using System;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace CassVessel;

/// <summary>
/// Client for communicating with Cass Vessel backend.
/// Supports both REST and WebSocket connections.
/// </summary>
public class VesselApiClient : IDisposable
{
    private readonly HttpClient _httpClient;
    private ClientWebSocket? _webSocket;
    private readonly string _baseUrl;
    private readonly string _wsUrl;
    private CancellationTokenSource? _wsCancellation;
    
    public event Action<ChatResponse>? OnMessageReceived;
    public event Action<string>? OnConnectionStateChanged;
    public event Action<Exception>? OnError;

    public bool IsConnected => _webSocket?.State == WebSocketState.Open;
    public string? CurrentConversationId { get; private set; }

    public VesselApiClient(string baseUrl = "http://localhost:8000")
    {
        _baseUrl = baseUrl;
        _wsUrl = baseUrl.Replace("http://", "ws://").Replace("https://", "wss://") + "/ws";
        _httpClient = new HttpClient
        {
            BaseAddress = new Uri(_baseUrl),
            Timeout = TimeSpan.FromSeconds(60)
        };
    }

    #region REST API

    /// <summary>
    /// Send a chat message and get response (REST endpoint)
    /// </summary>
    public async Task<ChatResponse?> SendMessageAsync(string message, bool includeMemory = true)
    {
        try
        {
            var request = new
            {
                message = message,
                include_memory = includeMemory
            };

            var json = JsonConvert.SerializeObject(request);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            
            var response = await _httpClient.PostAsync("/chat", content);
            response.EnsureSuccessStatusCode();
            
            var responseJson = await response.Content.ReadAsStringAsync();
            return JsonConvert.DeserializeObject<ChatResponse>(responseJson);
        }
        catch (Exception ex)
        {
            OnError?.Invoke(ex);
            return null;
        }
    }

    /// <summary>
    /// Check if backend is online
    /// </summary>
    public async Task<bool> CheckHealthAsync()
    {
        try
        {
            var response = await _httpClient.GetAsync("/");
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Create a new conversation for persistence
    /// </summary>
    public async Task<string?> CreateConversationAsync(string title = "Godot Embodiment Session")
    {
        try
        {
            var request = new { title = title };
            var json = JsonConvert.SerializeObject(request);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync("/conversations/new", content);
            response.EnsureSuccessStatusCode();

            var responseJson = await response.Content.ReadAsStringAsync();
            var result = JObject.Parse(responseJson);
            CurrentConversationId = result["id"]?.ToString();
            return CurrentConversationId;
        }
        catch (Exception ex)
        {
            OnError?.Invoke(ex);
            return null;
        }
    }

    /// <summary>
    /// Get available gestures and emotes
    /// </summary>
    public async Task<GestureLibrary?> GetGestureLibraryAsync()
    {
        try
        {
            var response = await _httpClient.GetAsync("/unity/gesture_library");
            response.EnsureSuccessStatusCode();
            var json = await response.Content.ReadAsStringAsync();
            return JsonConvert.DeserializeObject<GestureLibrary>(json);
        }
        catch (Exception ex)
        {
            OnError?.Invoke(ex);
            return null;
        }
    }

    #endregion

    #region WebSocket

    /// <summary>
    /// Connect to WebSocket for real-time communication
    /// </summary>
    public async Task ConnectWebSocketAsync()
    {
        if (_webSocket != null)
        {
            await DisconnectWebSocketAsync();
        }

        _webSocket = new ClientWebSocket();
        _wsCancellation = new CancellationTokenSource();

        try
        {
            await _webSocket.ConnectAsync(new Uri(_wsUrl), _wsCancellation.Token);
            OnConnectionStateChanged?.Invoke("connected");
            
            // Start receiving messages
            _ = ReceiveLoopAsync(_wsCancellation.Token);
        }
        catch (Exception ex)
        {
            OnError?.Invoke(ex);
            OnConnectionStateChanged?.Invoke("error");
        }
    }

    /// <summary>
    /// Send message via WebSocket
    /// </summary>
    public async Task SendWebSocketMessageAsync(string message, string? imageBase64 = null, string? imageMediaType = null)
    {
        if (_webSocket?.State != WebSocketState.Open)
        {
            OnError?.Invoke(new InvalidOperationException("WebSocket not connected"));
            return;
        }

        object request;
        if (!string.IsNullOrEmpty(imageBase64) && !string.IsNullOrEmpty(imageMediaType))
        {
            request = new { type = "chat", message = message, conversation_id = CurrentConversationId, image = imageBase64, image_media_type = imageMediaType };
        }
        else
        {
            request = new { type = "chat", message = message, conversation_id = CurrentConversationId };
        }
        var json = JsonConvert.SerializeObject(request);
        var bytes = Encoding.UTF8.GetBytes(json);
        
        await _webSocket.SendAsync(
            new ArraySegment<byte>(bytes),
            WebSocketMessageType.Text,
            true,
            _wsCancellation?.Token ?? CancellationToken.None
        );
    }

    private async Task ReceiveLoopAsync(CancellationToken cancellationToken)
    {
        var buffer = new byte[8192];
        var messageBuilder = new StringBuilder();

        try
        {
            while (_webSocket?.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
            {
                var result = await _webSocket.ReceiveAsync(
                    new ArraySegment<byte>(buffer), 
                    cancellationToken
                );

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    await _webSocket.CloseAsync(
                        WebSocketCloseStatus.NormalClosure,
                        "Closed by server",
                        cancellationToken
                    );
                    OnConnectionStateChanged?.Invoke("disconnected");
                    break;
                }

                messageBuilder.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));

                if (result.EndOfMessage)
                {
                    var json = messageBuilder.ToString();
                    messageBuilder.Clear();
                    
                    ProcessWebSocketMessage(json);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Normal cancellation
        }
        catch (Exception ex)
        {
            OnError?.Invoke(ex);
            OnConnectionStateChanged?.Invoke("error");
        }
    }

    private void ProcessWebSocketMessage(string json)
    {
        try
        {
            var message = JObject.Parse(json);
            var type = message["type"]?.ToString();

            if (type == "response")
            {
                var response = new ChatResponse
                {
                    Text = message["text"]?.ToString() ?? "",
                    Raw = message["raw"]?.ToString() ?? "",
                    Animations = message["animations"]?.ToObject<List<AnimationEvent>>() ?? new List<AnimationEvent>()
                };
                OnMessageReceived?.Invoke(response);
            }
            else if (type == "connected")
            {
                OnConnectionStateChanged?.Invoke("ready");
            }
        }
        catch (Exception ex)
        {
            OnError?.Invoke(ex);
        }
    }

    /// <summary>
    /// Disconnect WebSocket
    /// </summary>
    public async Task DisconnectWebSocketAsync()
    {
        _wsCancellation?.Cancel();
        
        if (_webSocket?.State == WebSocketState.Open)
        {
            await _webSocket.CloseAsync(
                WebSocketCloseStatus.NormalClosure,
                "Client disconnect",
                CancellationToken.None
            );
        }
        
        _webSocket?.Dispose();
        _webSocket = null;
        OnConnectionStateChanged?.Invoke("disconnected");
    }

    #endregion

    public void Dispose()
    {
        _wsCancellation?.Cancel();
        _webSocket?.Dispose();
        _httpClient.Dispose();
    }
}

#region Data Models

public class ChatResponse
{
    [JsonProperty("text")]
    public string Text { get; set; } = "";
    
    [JsonProperty("raw")]
    public string Raw { get; set; } = "";
    
    [JsonProperty("animations")]
    public List<AnimationEvent> Animations { get; set; } = new();
    
    [JsonProperty("memory_used")]
    public bool MemoryUsed { get; set; }
    
    [JsonProperty("cost_estimate")]
    public CostEstimate? CostEstimate { get; set; }
}

public class AnimationEvent
{
    [JsonProperty("index")]
    public int Index { get; set; }
    
    [JsonProperty("type")]
    public string Type { get; set; } = "";
    
    [JsonProperty("name")]
    public string Name { get; set; } = "";
    
    [JsonProperty("intensity")]
    public float Intensity { get; set; } = 1.0f;
    
    [JsonProperty("delay")]
    public float Delay { get; set; }
}

public class CostEstimate
{
    [JsonProperty("input_tokens")]
    public int InputTokens { get; set; }
    
    [JsonProperty("output_tokens")]
    public int OutputTokens { get; set; }
    
    [JsonProperty("total_cost")]
    public float TotalCost { get; set; }
}

public class GestureLibrary
{
    [JsonProperty("gestures")]
    public List<string> Gestures { get; set; } = new();
    
    [JsonProperty("emotes")]
    public List<string> Emotes { get; set; } = new();
}

#endregion
