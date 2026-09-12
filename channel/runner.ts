import { createServer } from "node:http";

import { createChannel } from "@copilotkit/channels";
import { slack } from "@copilotkit/channels/slack";
import {
  CopilotKitIntelligence,
  CopilotRuntime,
} from "@copilotkit/runtime/v2";
import { createCopilotNodeListener } from "@copilotkit/runtime/v2/node";
import { DisclosureDecision, POLICY_COMPONENTS, type DisclosureDecisionProps } from "./components.js";

type DecideResponse = {
  component: "DisclosureDecision";
  props: DisclosureDecisionProps;
};

import { DisclosureDecision, POLICY_COMPONENTS, type DisclosureDecisionProps } from "./components.js";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

<<<<<<< Updated upstream
type SlackTurnContext = {
  channelId: string;
  threadTs: string;
};

type PolicyResponse = {
  component: "DisclosureDecision";
  props: DisclosureDecisionProps;
};

/** Direct Slack turns are keyed as `<channel id>::<root thread timestamp>`. */
function parseSlackTurnContext(conversationKey: string): SlackTurnContext | null {
  const separator = conversationKey.indexOf("::");
  if (separator === -1) return null;

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
=======
async function requestDecision(input: {
  channel_id: string;
  user_id: string;
  text: string;
  thread_ts: string;
}): Promise<DecideResponse> {
  const baseUrl = required("POLICY_API_URL").replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/decide`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(`Policy API returned ${response.status}`);
  }
  return (await response.json()) as DecideResponse;
>>>>>>> Stashed changes
}

const channel = createChannel({
  name: required("CHANNEL_CODE"),
  identifyUser: "platform",
<<<<<<< Updated upstream
  adapters: [
    slack({
      botToken: required("SLACK_BOT_TOKEN"),
      appToken: required("SLACK_APP_TOKEN"),
      assistant: false,
      streaming: "legacy",
    }),
  ],
  components: [...POLICY_COMPONENTS],
});

channel.onMention(async ({ thread, message }) => {
  const context = parseSlackTurnContext(thread.conversationKey);
  if (message.platform !== "slack" || context === null) {
    await thread.post("I could not safely identify this Slack conversation.");
    return;
  }

  try {
    const decision = await requestDecision(context, message.actor.id, message.text);
    await thread.post(DisclosureDecision(decision.props));
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    console.error(`Policy request failed: ${detail}`);
    await thread.post("Need To Know is temporarily unavailable. Please try again shortly.");
=======
  components: POLICY_COMPONENTS,
});

channel.onMention(async ({ thread, message }) => {
  try {
    console.dir(
      {
        decisionRequest: {
          conversationKey: thread.conversationKey,
          messageRefId: message.ref.id,
          userId: message.user?.id ?? message.actor.id,
        },
      },
      { depth: null },
    );
    const decision = await requestDecision({
      // Channels' stable conversation key is the provider conversation id
      // carried into this typed boundary; the runner performs no Slack reads.
      channel_id: thread.conversationKey,
      user_id: message.user?.id ?? message.actor.id,
      text: message.text,
      thread_ts: message.ref.id,
    });
    await thread.post(DisclosureDecision(decision.props));
  } catch (error) {
    console.error("Need to Know decision request failed", error);
    await thread.post("I could not safely evaluate that request. Please try again.");
>>>>>>> Stashed changes
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
  console.log(`Slack Channel online; lifecycle server listening on :${port}`);
});
