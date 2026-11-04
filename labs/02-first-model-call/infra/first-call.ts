// Calls a model through AI Gateway with the OpenAI npm package: once with the Responses API and once with
// Chat Completions. The SDK sends the gateway key as a bearer token, which the model endpoint accepts.
//
// Usage (Node.js 22.18 or later runs TypeScript directly; on older versions use `npx tsx first-call.ts`):
//   npm install
//   export AI_GATEWAY_URL="<gateway-url>"
//   export AI_GATEWAY_MODEL="<model-name>"
//   export AI_GATEWAY_API_KEY="..."      // never commit this value
//   node first-call.ts
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

const response = await client.responses.create({
  model,
  input: "Write a one-sentence status update.",
});
console.log(`Responses API:    ${response.output_text}`);

const completion = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Describe an AI gateway in one sentence." }],
});
console.log(`Chat Completions: ${completion.choices[0].message.content}`);
console.log(`Tokens used:      ${completion.usage?.total_tokens ?? "n/a"}`);
