using Godot;
using System;

namespace CassVessel;

/// <summary>
/// Main scene controller.
/// Manages UI, API communication, and avatar coordination.
/// </summary>
public partial class Main : Node3D
{
    [Export]
    public NodePath? AvatarPath { get; set; }
    
    [Export]
    public NodePath? ChatInputPath { get; set; }
    
    [Export]
    public NodePath? ChatDisplayPath { get; set; }
    
    [Export]
    public NodePath? StatusLabelPath { get; set; }
    
    [Export]
    public string BackendUrl { get; set; } = "http://localhost:8000";
    
    [Export]
    public bool UseWebSocket { get; set; } = true;

    private CassAvatar? _avatar;
    private LineEdit? _chatInput;
    private RichTextLabel? _chatDisplay;
    private Label? _statusLabel;
    private VesselApiClient? _apiClient;

    private bool _isConnected;
    private readonly System.Collections.Concurrent.ConcurrentQueue<ChatResponse> _pendingResponses = new();

    // Image attachment
    private FileDialog? _fileDialog;
    private string? _pendingImageBase64;
    private string? _pendingImageMediaType;
    private Button? _attachButton;

    public override void _Ready()
    {
        GD.Print("=== CASS VESSEL STARTING ===");
        GD.Print("First Contact Embodiment System");
        GD.Print("============================");
        
        // Get node references
        if (AvatarPath != null)
            _avatar = GetNode<CassAvatar>(AvatarPath);
        if (ChatInputPath != null)
            _chatInput = GetNode<LineEdit>(ChatInputPath);
        if (ChatDisplayPath != null)
            _chatDisplay = GetNode<RichTextLabel>(ChatDisplayPath);
        if (StatusLabelPath != null)
            _statusLabel = GetNode<Label>(StatusLabelPath);
        
        // Initialize API client
        _apiClient = new VesselApiClient(BackendUrl);
        _apiClient.OnMessageReceived += HandleMessageReceived;
        _apiClient.OnConnectionStateChanged += HandleConnectionStateChanged;
        _apiClient.OnError += HandleError;
        
        // Setup input handling
        if (_chatInput != null)
        {
            _chatInput.TextSubmitted += OnChatSubmitted;
        }

        // Setup file dialog for image attachment
        SetupFileDialog();

        // Setup attach button
        _attachButton = GetNodeOrNull<Button>("UI/ChatContainer/InputRow/AttachButton");
        if (_attachButton != null)
        {
            _attachButton.Pressed += OnAttachButtonPressed;
        }

        // Connect to backend
        _ = ConnectToBackend();
    }

    public override void _ExitTree()
    {
        _apiClient?.Dispose();
    }

    public override void _Input(InputEvent @event)
    {
        // Focus chat input on Enter key if not already focused
        if (@event is InputEventKey keyEvent && keyEvent.Pressed && keyEvent.Keycode == Key.Enter)
        {
            if (_chatInput != null && !_chatInput.HasFocus())
            {
                _chatInput.GrabFocus();
            }
        }
        
        // Quick reconnect on R key
        if (@event is InputEventKey rKey && rKey.Pressed && rKey.Keycode == Key.R && rKey.CtrlPressed)
        {
            _ = ConnectToBackend();
        }
    }

    private async System.Threading.Tasks.Task ConnectToBackend()
    {
        UpdateStatus("Connecting to vessel backend...");
        
        if (_apiClient == null) return;
        
        // Check if backend is online
        var isOnline = await _apiClient.CheckHealthAsync();
        
        if (!isOnline)
        {
            UpdateStatus("Backend offline. Start with: python main.py");
            AppendChat("[SYSTEM]", "Backend not reachable at " + BackendUrl, Colors.Red);
            return;
        }

        // Create a conversation for this session so messages are persisted
        var conversationId = await _apiClient.CreateConversationAsync("First Contact - Embodiment");
        if (conversationId != null)
        {
            GD.Print($"Created conversation: {conversationId}");
            AppendChat("[SYSTEM]", "Conversation created - messages will be remembered", new Color(0.5f, 0.8f, 0.5f));
        }
        else
        {
            AppendChat("[SYSTEM]", "Warning: Could not create conversation - messages may not persist", Colors.Yellow);
        }

        if (UseWebSocket)
        {
            await _apiClient.ConnectWebSocketAsync();
        }
        else
        {
            _isConnected = true;
            UpdateStatus("Connected (REST mode)");
            AppendChat("[SYSTEM]", "Connected to Cass Vessel backend", Colors.Green);
        }
    }

    private void HandleConnectionStateChanged(string state)
    {
        CallDeferred(nameof(ProcessConnectionState), state);
    }

    private void ProcessConnectionState(string state)
    {
        switch (state)
        {
            case "connected":
                UpdateStatus("WebSocket connected, initializing...");
                break;
            case "ready":
                _isConnected = true;
                UpdateStatus("Connected - Cass is online");
                AppendChat("[SYSTEM]", "Connection established. Cass is ready.", Colors.Green);
                break;
            case "disconnected":
                _isConnected = false;
                UpdateStatus("Disconnected - Press Ctrl+R to reconnect");
                AppendChat("[SYSTEM]", "Connection lost.", Colors.Yellow);
                break;
            case "error":
                _isConnected = false;
                UpdateStatus("Connection error");
                break;
        }
    }

    private void HandleMessageReceived(ChatResponse response)
    {
        // Queue for processing on main thread (CallDeferred can't handle custom types in Godot 4.5)
        _pendingResponses.Enqueue(response);
    }

    public override void _Process(double delta)
    {
        // Process any pending responses on main thread
        while (_pendingResponses.TryDequeue(out var response))
        {
            ProcessResponse(response);
        }
    }

    private void ProcessResponse(ChatResponse response)
    {
        // Display text
        AppendChat("[Cass]", response.Text, new Color(0.4f, 0.8f, 1.0f));
        
        // Trigger animations
        if (_avatar != null && response.Animations.Count > 0)
        {
            _avatar.QueueAnimations(response.Animations);
        }
        
        // Log cost
        if (response.CostEstimate != null)
        {
            GD.Print($"API Cost: ${response.CostEstimate.TotalCost:F4}");
        }
    }

    private void HandleError(Exception ex)
    {
        CallDeferred(nameof(ProcessError), ex.Message);
    }

    private void ProcessError(string message)
    {
        GD.PrintErr($"API Error: {message}");
        AppendChat("[ERROR]", message, Colors.Red);
    }

    private async void OnChatSubmitted(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        if (!_isConnected)
        {
            AppendChat("[SYSTEM]", "Not connected to backend", Colors.Yellow);
            return;
        }

        // Clear input
        if (_chatInput != null)
        {
            _chatInput.Text = "";
        }

        // Display user message (note if image is attached)
        var displayText = _pendingImageBase64 != null ? $"{text} [📷 image attached]" : text;
        AppendChat("[You]", displayText, new Color(0.8f, 0.8f, 0.8f));

        // Send to backend
        if (_apiClient != null)
        {
            if (UseWebSocket)
            {
                await _apiClient.SendWebSocketMessageAsync(text, _pendingImageBase64, _pendingImageMediaType);
            }
            else
            {
                var response = await _apiClient.SendMessageAsync(text);
                if (response != null)
                {
                    ProcessResponse(response);
                }
            }
        }

        // Clear the pending image after sending
        ClearPendingImage();
    }

    private void UpdateStatus(string status)
    {
        if (_statusLabel != null)
        {
            _statusLabel.Text = status;
        }
        GD.Print($"[Status] {status}");
    }

    private void AppendChat(string sender, string message, Color color)
    {
        if (_chatDisplay == null) return;
        
        var timestamp = DateTime.Now.ToString("HH:mm:ss");
        var colorHex = color.ToHtml(false);
        
        _chatDisplay.AppendText($"\n[color=gray][{timestamp}][/color] ");
        _chatDisplay.AppendText($"[color=#{colorHex}]{sender}[/color] ");
        _chatDisplay.AppendText(message);

        // Auto-scroll to bottom
        _chatDisplay.ScrollToLine(_chatDisplay.GetLineCount());
    }

    #region Image Attachment

    private void SetupFileDialog()
    {
        _fileDialog = new FileDialog
        {
            FileMode = FileDialog.FileModeEnum.OpenFile,
            Access = FileDialog.AccessEnum.Filesystem,
            Title = "Select Image to Show Cass",
            Size = new Vector2I(800, 600)
        };
        _fileDialog.AddFilter("*.png, *.jpg, *.jpeg, *.webp", "Images");
        _fileDialog.FileSelected += OnFileSelected;
        AddChild(_fileDialog);
    }

    private void OnAttachButtonPressed()
    {
        _fileDialog?.PopupCentered();
    }

    private void OnFileSelected(string path)
    {
        try
        {
            // Read the file using Godot's FileAccess
            var file = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
            if (file == null)
            {
                AppendChat("[ERROR]", $"Could not open file: {path}", Colors.Red);
                return;
            }

            var bytes = file.GetBuffer((long)file.GetLength());
            file.Close();

            // Convert to base64
            _pendingImageBase64 = Convert.ToBase64String(bytes);

            // Determine media type from extension
            var ext = path.GetExtension().ToLower();
            _pendingImageMediaType = ext switch
            {
                "png" => "image/png",
                "jpg" or "jpeg" => "image/jpeg",
                "webp" => "image/webp",
                "gif" => "image/gif",
                _ => "image/png"
            };

            var fileName = path.GetFile();
            AppendChat("[SYSTEM]", $"Image attached: {fileName} (send a message to include it)", new Color(0.5f, 0.8f, 0.5f));

            // Update attach button to show there's a pending image
            if (_attachButton != null)
            {
                _attachButton.Text = "📎 ✓";
            }

            GD.Print($"Image loaded: {fileName}, {bytes.Length} bytes, type: {_pendingImageMediaType}");
        }
        catch (Exception ex)
        {
            AppendChat("[ERROR]", $"Failed to load image: {ex.Message}", Colors.Red);
        }
    }

    private void ClearPendingImage()
    {
        _pendingImageBase64 = null;
        _pendingImageMediaType = null;
        if (_attachButton != null)
        {
            _attachButton.Text = "📎";
        }
    }

    #endregion
}
