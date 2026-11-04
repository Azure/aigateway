// Calls a model through AI Gateway with a Microsoft Entra ID access token instead of an API key.
//
// DefaultAzureCredential picks up your Azure CLI or Visual Studio Code sign-in on a laptop, and a managed
// identity or workload identity when the code runs in Azure. getBearerTokenProvider returns a cached token
// and refreshes it before it expires. The OpenAI package (5.18 or later) calls the provider before every
// request and sends the result as `Authorization: Bearer <token>`.
//
// Usage (Node.js 22.18 or later runs TypeScript directly; on older versions use `npx tsx call-with-entra.ts`):
//   npm install
//   az login
//   export AI_GATEWAY_URL="<gateway-url>"
//   export AI_GATEWAY_MODEL="<model-name>"
//   node call-with-entra.ts
import { DefaultAzureCredential, getBearerTokenProvider } from "@azure/identity";
import OpenAI from "openai";

// App-only and managed identity callers must use /.default. It also works for an Azure CLI sign-in.
const AI_GATEWAY_SCOPE = "https://azure-api.net/aigateway/.default";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} before running this sample.`);
  return value;
}

const gatewayUrl: string = required("AI_GATEWAY_URL").replace(/\/+$/, "");
const model: string = required("AI_GATEWAY_MODEL");

const getToken = getBearerTokenProvider(new DefaultAzureCredential(), AI_GATEWAY_SCOPE);

const client = new OpenAI({
  baseURL: `${gatewayUrl}/default/models/openai/v1`,
  apiKey: getToken,
});

const completion = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "In one sentence, why use Microsoft Entra ID instead of API keys?" }],
});
console.log(`Model reply: ${completion.choices[0].message.content}`);
console.log(`Tokens used: ${completion.usage?.total_tokens ?? "n/a"}`);
