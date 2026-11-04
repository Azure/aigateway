// Streams a reply through AI Gateway with the OpenAI npm package: once with Chat Completions and once with the
// Responses API. Each stream prints text as it arrives and then the token usage from the end of the stream.
//
// Usage (Node.js 22.18 or later runs TypeScript directly; on older versions use `npx tsx stream.ts`):
//   npm install
//   export AI_GATEWAY_URL="<gateway-url>"
//   export AI_GATEWAY_MODEL="<model-name>"
//   export AI_GATEWAY_API_KEY="..."      // never commit this value
//   node stream.ts
import OpenAI from "openai";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} before running this sample.`);
  return value;
}

const gatewayUrl: string = required("AI_GATEWAY_URL").replace(/\/+$/, "");
const model: string = required("AI_GATEWAY_MODEL");

const client = new OpenAI({
  baseURL: `${gatewayUrl}/default/models/openai/v1`,
  apiKey: required("AI_GATEWAY_API_KEY"),
});

console.log("Chat Completions:");
const started = performance.now();
let firstToken: number | undefined;
let usage: OpenAI.CompletionUsage | undefined;
const stream = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Explain in two sentences why streaming makes chat apps feel faster." }],
  stream: true,
  // Ask for a final usage chunk. It arrives with an empty choices array, just before the stream ends.
  stream_options: { include_usage: true },
});
for await (const chunk of stream) {
  if (chunk.usage) usage = chunk.usage;
  // The first chunk (prompt filter results) and the usage chunk have no choices.
  const text = chunk.choices[0]?.delta?.content;
  if (text) {
    firstToken ??= (performance.now() - started) / 1000;
    process.stdout.write(text);
  }
}
console.log(`\nFirst token:      ${firstToken === undefined ? "-" : `${firstToken.toFixed(2)} s`}`);
console.log(usage
  ? `Tokens used:      ${usage.total_tokens} (prompt ${usage.prompt_tokens}, completion ${usage.completion_tokens})`
  : "Tokens used:      no usage chunk");

console.log("\nResponses API:");
const events = await client.responses.create({
  model,
  input: "Write a one-sentence status update about streaming.",
  stream: true,
});
for await (const event of events) {
  if (event.type === "response.output_text.delta") {
    process.stdout.write(event.delta);
  } else if (event.type === "response.completed") {
    // The Responses API always reports usage in its final event.
    const done = event.response.usage;
    console.log(`\nTokens used:      ${done?.total_tokens} (input ${done?.input_tokens}, output ${done?.output_tokens})`);
  }
}
