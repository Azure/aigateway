// Calls a model through AI Gateway with a Microsoft Entra ID access token instead of an API key.
//
// DefaultAzureCredential picks up your Azure CLI or Visual Studio sign-in on a laptop, and a managed identity
// or workload identity when the code runs in Azure. Request a new token for each call: the credential caches
// tokens and refreshes them before they expire.
//
// Usage:
//   az login
//   export AI_GATEWAY_URL="<gateway-url>"
//   export AI_GATEWAY_MODEL="<model-name>"
//   dotnet run
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Azure.Core;
using Azure.Identity;

// App-only and managed identity callers must use /.default. It also works for an Azure CLI sign-in.
const string AiGatewayScope = "https://azure-api.net/aigateway/.default";

static string Required(string name) =>
    Environment.GetEnvironmentVariable(name) is { Length: > 0 } value
        ? value
        : throw new InvalidOperationException($"Set {name} before running this sample.");

var gatewayUrl = Required("AI_GATEWAY_URL").TrimEnd('/');
var model = Required("AI_GATEWAY_MODEL");

var credential = new DefaultAzureCredential();
AccessToken token = await credential.GetTokenAsync(new TokenRequestContext(new[] { AiGatewayScope }));

using var http = new HttpClient();
using var request = new HttpRequestMessage(HttpMethod.Post, $"{gatewayUrl}/default/models/openai/v1/chat/completions")
{
    Content = JsonContent.Create(new
    {
        model,
        messages = new[] { new { role = "user", content = "In one sentence, why use Microsoft Entra ID instead of API keys?" } },
    }),
};
request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);

using var response = await http.SendAsync(request);
var body = await response.Content.ReadAsStringAsync();
if (!response.IsSuccessStatusCode)
{
    Console.Error.WriteLine($"{(int)response.StatusCode} {response.ReasonPhrase}: {body}");
    return 1;
}

using var json = JsonDocument.Parse(body);
var reply = json.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString();
Console.WriteLine($"Model reply: {reply}");
var tokensUsed = json.RootElement.TryGetProperty("usage", out var usage) ? usage.GetProperty("total_tokens").ToString() : "n/a";
Console.WriteLine($"Tokens used: {tokensUsed}");
return 0;
