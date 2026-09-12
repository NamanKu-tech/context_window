import { createServer } from "node:http";

import { createChannel } from "@copilotkit/channels";
import {
  CopilotKitIntelligence,
  CopilotRuntime,
} from "@copilotkit/runtime/v2";
import { createCopilotNodeListener } from "@copilotkit/runtime/v2/node";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

const channel = createChannel({
  name: required("CHANNEL_CODE"),
  identifyUser: "platform",
});

channel.onMention(async ({ thread, message }) => {
  // The Channels message object carries internal SDK state. Record only the
  // public, normalized message fields required for the P2 handshake.
  const handshakeFields = {
    text: message.text,
    userId: message.user?.id,
    actorId: message.actor.id,
    platform: message.platform,
    messageRefId: message.ref.id,
    operation: message.operation,
    eventId: message.eventId,
    turnId: message.turnId,
    deliveryId: message.deliveryId,
  };
  console.dir({ channelMessage: handshakeFields }, { depth: null });
  await thread.post("P2 handshake received. Slack delivery is working.");
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
if (status.overall !== "online") {
  throw new Error(`Slack Channel is not online: ${JSON.stringify(status)}`);
}

const port = Number(process.env.PORT ?? 3000);
server.listen(port, () => {
  console.log(`Slack Channel online; lifecycle server listening on :${port}`);
});
