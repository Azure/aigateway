// Calls a model through AI Gateway with HttpClient: once with the Responses API and once with
// Chat Completions. The api-key header stays explicit, as in the .NET samples in the AI Gateway docs.
//
// Usage:
//   export AI_GATEWAY_URL="<gateway-url>"
//   export AI_GATEWAY_MODEL="<model-name>"
//   export AI_GATEWAY_API_KEY="..."      // never commit this value
//   dotnet run
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;

static string Required(string name) =>
    Environment.GetEnvironmentVariable(name) is { Length: > 0 } value
        ? value
        : throw new InvalidOperationException($"Set {name} before running this sample.");

var gatewayUrl = Required("AI_GATEWAY_URL").TrimEnd('/');
var model = Required("AI_GATEWAY_MODEL");

using var http = new HttpClient { BaseAddress = new Uri($"{gatewayUrl}/default/models/openai/v1/") };
http.DefaultRequestHeaders.Add("api-key", Required("AI_GATEWAY_API_KEY"));

// Responses API: the text is in output[] items of type "message", in content parts of type "output_text".
using (var reply = await http.PostAsJsonAsync("responses", new
{
    model,
    input = "Write a one-sentence status update.",
}))
{
    using var json = await ReadJsonAsync(reply);
    var text = new StringBuilder();
    foreach (var item in json.RootElement.GetProperty("output").EnumerateArray())
    {
        if (item.GetProperty("type").GetString() != "message") continue;
        foreach (var part in item.GetProperty("content").EnumerateArray())
        {
            if (part.GetProperty("type").GetString() == "output_text")
            {
                text.Append(part.GetProperty("text").GetString());
            }
        }
    }
    Console.WriteLine($"Responses API:    {text}");
}

// Chat Completions
using (var reply = await http.PostAsJsonAsync("chat/completions", new
{
    model,
    messages = new[] { new { role = "user", content = "Describe an AI gateway in one sentence." } },
}))
{
    using var json = await ReadJsonAsync(reply);
    var content = json.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString();
    Console.WriteLine($"Chat Completions: {content}");
}

static async Task<JsonDocument> ReadJsonAsync(HttpResponseMessage reply)
{
    var body = await reply.Content.ReadAsStringAsync();
    if (!reply.IsSuccessStatusCode)
    {
        throw new HttpRequestException($"HTTP {(int)reply.StatusCode}: {body}");
    }
    return JsonDocument.Parse(body);
}
