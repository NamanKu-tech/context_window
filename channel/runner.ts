import { createServer } from "node:http";
import { appendFile } from "node:fs/promises";

import { createChannel } from "@copilotkit/channels";
import {
  CopilotKitIntelligence,
  CopilotRuntime,
} from "@copilotkit/runtime/v2";
import { createCopilotNodeListener } from "@copilotkit/runtime/v2/node";
import { DisclosureDecision, POLICY_COMPONENTS, type DisclosureDecisionProps } from "./components.js";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

const RUNTIME_LOG = "/private/tmp/need-to-know-runtime.log";

function logRuntime(event: string): Promise<void> {
  return appendFile(RUNTIME_LOG, `${new Date().toISOString()} ${event}\n`).catch(() => undefined);
}

type SlackTurnContext = {
  channelId: string;
  threadTs: string;
};

type PolicyResponse = {
  component: "DisclosureDecision";
  props: DisclosureDecisionProps;
};

type BrokerReplyResponse = { message: string };

function parseBrokerReply(text: string): { requestId: string; approved: boolean } | null {
  const match = /(?:^|\s)(approve|deny)\s+([a-f0-9]{8})\s*$/i.exec(text);
  return match
    ? { requestId: match[2], approved: match[1].toLowerCase() === "approve" }
    : null;
}

/** Direct Slack turns are keyed as `<channel id>::<root thread timestamp>`.
 * Managed Intelligence supplies an opaque UUID; policy_api resolves that to
 * its real Slack channel before building the venue. */
function parseSlackTurnContext(conversationKey: string): SlackTurnContext | null {
  const separator = conversationKey.indexOf("::");
  if (separator === -1) {
    return /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(conversationKey)
      ? { channelId: conversationKey, threadTs: conversationKey }
      : null;
  }

  const channelId = conversationKey.slice(0, separator);
  const threadTs = conversationKey.slice(separator + 2);
  return /^[CDG][A-Z0-9]+$/.test(channelId) && /^\d{10}\.\d{6}$/.test(threadTs)
    ? { channelId, threadTs }
    : null;
}

async function requestDecision(
  context: SlackTurnContext,
  userId: string,
  text: string,
): Promise<PolicyResponse> {
  const apiUrl = required("POLICY_API_URL").replace(/\/$/, "");
  const response = await fetch(`${apiUrl}/decide`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      channel_id: context.channelId,
      user_id: userId,
      text,
      thread_ts: context.threadTs,
    }),
  });

  if (!response.ok) {
    throw new Error(`Policy API returned HTTP ${response.status}`);
  }

  const payload: unknown = await response.json();
  if (
    !payload ||
    typeof payload !== "object" ||
    !("component" in payload) ||
    payload.component !== "DisclosureDecision" ||
    !("props" in payload)
  ) {
    throw new Error("Policy API returned an unsupported component");
  }

  return payload as PolicyResponse;
}

async function recordBrokerReply(userId: string, requestId: string, approved: boolean): Promise<BrokerReplyResponse> {
  const apiUrl = required("POLICY_API_URL").replace(/\/$/, "");
  const response = await fetch(`${apiUrl}/broker/respond`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ request_id: requestId, responder_id: userId, approved }),
  });
  if (!response.ok) throw new Error(`Broker API returned HTTP ${response.status}`);
  return (await response.json()) as BrokerReplyResponse;
}

const channel = createChannel({
  name: required("CHANNEL_CODE"),
  identifyUser: "platform",
  components: [...POLICY_COMPONENTS],
});

channel.onMention(async ({ thread, message }) => {
  const brokerReply = parseBrokerReply(message.text);
  if (message.platform === "slack" && brokerReply) {
    try {
      const result = await recordBrokerReply(message.actor.id, brokerReply.requestId, brokerReply.approved);
      await logRuntime("broker reply recorded via mention");
      await thread.post(result.message);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "unknown error";
      await logRuntime(`broker error=${detail}`);
      await thread.post("I could not record that approval. The disclosure remains held.");
    }
    return;
  }

  const context = parseSlackTurnContext(thread.conversationKey);
  await logRuntime(
    `mention platform=${message.platform} context=${context ? "valid" : "invalid"} key=${thread.conversationKey}`,
  );
  if (message.platform !== "slack" || context === null) {
    await thread.post("I could not safely identify this Slack conversation.");
    return;
  }

  try {
    const decision = await requestDecision(context, message.actor.id, message.text);
    await logRuntime(`policy action=${decision.props.action}`);
    await thread.post(DisclosureDecision(decision.props));
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    console.error(`Policy request failed: ${detail}`);
    await logRuntime(`policy error=${detail}`);
    await thread.post("Need To Know is temporarily unavailable. Please try again shortly.");
  }
});

// The owner receives a DM containing this short code.  Keeping the approval
// text-only makes it reliable on the managed Slack adapter; the API still
// validates that only the recorded owner can complete it.
channel.onMessage(async ({ thread, message }) => {
  if (message.platform !== "slack") return;
  const brokerReply = parseBrokerReply(message.text);
  if (!brokerReply) return;
  try {
    const result = await recordBrokerReply(message.actor.id, brokerReply.requestId, brokerReply.approved);
    await thread.post(result.message);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    await logRuntime(`broker error=${detail}`);
    await thread.post("I could not record that approval. The disclosure remains held.");
  }
});

const intelligence = new CopilotKitIntelligence({
  apiKey: required("CPK_INTELLIGENCE_API_KEY"),
  apiUrl: process.env.INTELLIGENCE_API_URL,
  wsUrl: process.env.INTELLIGENCE_GATEWAY_WS_URL,
});

const runtime = new CopilotRuntime({
  agents: {},
  intelligence,
  channels: [channel],
});

let teardown: (() => Promise<void>) | undefined;
const shutdown = async (): Promise<void> => {
  await teardown?.();
};
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);

const listener = createCopilotNodeListener({
  runtime,
  basePath: "/api/copilotkit",
});
const channels = listener.channels;
const server = createServer(listener);

teardown = async (): Promise<void> => {
  await channels.stop();
  if (server.listening) {
    server.close();
  }
};

await channels.ready({ timeoutMs: 30_000 });
const status = channels.status();
if (status.overall === "error" || status.overall === "stopped") {
  throw new Error(`Channels could not start: ${JSON.stringify(status)}`);
}

const port = Number(process.env.PORT ?? 3000);
server.listen(port, () => {
  void logRuntime("runner online build=policy-ui-v3");
  console.log(`Slack Channel online; lifecycle server listening on :${port}`);
});
