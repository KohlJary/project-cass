using Godot;
using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace CassVessel;

/// <summary>
/// Main controller for Cass's avatar.
/// Handles animation, positioning, and visual state.
/// </summary>
public partial class CassAvatar : Node3D
{
    [Export]
    public NodePath? AnimationPlayerPath { get; set; }
    
    [Export]
    public NodePath? MeshInstancePath { get; set; }
    
    [Export]
    public Color HologramColor { get; set; } = new Color(0.3f, 0.7f, 0.9f, 0.85f); // Soft cyan hologram

    [Export]
    public float HologramFlickerIntensity { get; set; } = 0.03f; // Subtler flicker

    [Export]
    public float IdleBobbingSpeed { get; set; } = 1.2f; // Slower, more serene

    [Export]
    public float IdleBobbingAmount { get; set; } = 0.015f; // Gentler movement

    [Export]
    public float IdleRotationSpeed { get; set; } = 0.1f; // Subtle rotation

    private AnimationPlayer? _animationPlayer;
    private MeshInstance3D? _meshInstance;
    private ShaderMaterial? _hologramMaterial;
    
    private Vector3 _basePosition;
    private Quaternion _baseRotation;
    private float _timeAccumulator;
    private Queue<AnimationEvent> _animationQueue = new();
    private bool _isProcessingAnimation;
    
    // Current emotional state
    private string _currentGesture = "idle";
    private string _currentEmote = "neutral";
    private float _currentIntensity = 1.0f;

    public override void _Ready()
    {
        // Get references
        if (AnimationPlayerPath != null)
            _animationPlayer = GetNode<AnimationPlayer>(AnimationPlayerPath);
        
        if (MeshInstancePath != null)
            _meshInstance = GetNode<MeshInstance3D>(MeshInstancePath);
        
        _basePosition = Position;
        _baseRotation = Quaternion;

        // Setup hologram shader
        SetupHologramMaterial();
        
        GD.Print("Cass Avatar initialized. Ready for embodiment.");
    }

    public override void _Process(double delta)
    {
        _timeAccumulator += (float)delta;
        
        // Idle bobbing and rotation
        ProcessIdleAnimation();

        // Hologram flicker effect
        ProcessHologramFlicker();
        
        // Process animation queue
        ProcessAnimationQueue();
    }

    private void ProcessIdleAnimation()
    {
        // Gentle bobbing
        var bobOffset = Mathf.Sin(_timeAccumulator * IdleBobbingSpeed) * IdleBobbingAmount;
        Position = _basePosition + new Vector3(0, bobOffset, 0);

        // Subtle rotation - slow oscillation
        var rotAngle = Mathf.Sin(_timeAccumulator * IdleRotationSpeed) * 0.1f;
        Quaternion = _baseRotation * Quaternion.FromEuler(new Vector3(0, rotAngle, 0));
    }

    private void ProcessHologramFlicker()
    {
        if (_hologramMaterial == null) return;
        
        // Subtle random flicker
        var flicker = 1.0f - (GD.Randf() * HologramFlickerIntensity);
        _hologramMaterial.SetShaderParameter("emission_intensity", flicker);
    }

    private void SetupHologramMaterial()
    {
        // Create hologram shader material
        var shader = new Shader();
        shader.Code = @"
            shader_type spatial;
            render_mode blend_mix, depth_draw_opaque, cull_back;

            uniform vec4 hologram_color : source_color = vec4(0.4, 0.8, 1.0, 0.9);
            uniform float emission_intensity : hint_range(0.0, 2.0) = 1.0;
            uniform float scanline_speed : hint_range(0.0, 10.0) = 2.0;
            uniform float scanline_density : hint_range(0.0, 100.0) = 30.0;
            uniform float edge_glow : hint_range(0.0, 5.0) = 1.5;

            varying vec3 world_normal;
            varying vec3 world_position;

            void vertex() {
                world_normal = (MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz;
                world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
            }

            void fragment() {
                // Base hologram color
                ALBEDO = hologram_color.rgb;

                // Scanline effect
                float scanline = sin(world_position.y * scanline_density + TIME * scanline_speed) * 0.5 + 0.5;
                scanline = mix(0.8, 1.0, scanline);

                // Edge glow (fresnel)
                vec3 view_dir = normalize(CAMERA_POSITION_WORLD - world_position);
                float fresnel = pow(1.0 - max(dot(world_normal, view_dir), 0.0), edge_glow);

                // Combine effects
                EMISSION = hologram_color.rgb * emission_intensity * scanline * (1.0 + fresnel);
                ALPHA = hologram_color.a * scanline;
            }
        ";

        _hologramMaterial = new ShaderMaterial();
        _hologramMaterial.Shader = shader;
        _hologramMaterial.SetShaderParameter("hologram_color", HologramColor);
        _hologramMaterial.SetShaderParameter("emission_intensity", 1.2f);
        _hologramMaterial.SetShaderParameter("scanline_speed", 1.5f);  // Slower, less distracting
        _hologramMaterial.SetShaderParameter("scanline_density", 40.0f);  // Finer lines
        _hologramMaterial.SetShaderParameter("edge_glow", 2.0f);  // More pronounced rim

        // Apply to all MeshInstance3D children
        ApplyHologramToChildren(this);

        GD.Print("Hologram material applied to all meshes.");
    }

    private void ApplyHologramToChildren(Node node)
    {
        foreach (var child in node.GetChildren())
        {
            if (child is MeshInstance3D meshInstance)
            {
                meshInstance.MaterialOverride = _hologramMaterial;
                GD.Print($"Applied hologram to: {meshInstance.Name}");
            }
            // Recurse into children
            ApplyHologramToChildren(child);
        }
    }

    #region Animation System

    /// <summary>
    /// Queue animations from API response
    /// </summary>
    public void QueueAnimations(List<AnimationEvent> animations)
    {
        foreach (var anim in animations)
        {
            _animationQueue.Enqueue(anim);
        }
        
        GD.Print($"Queued {animations.Count} animations");
    }

    private async void ProcessAnimationQueue()
    {
        if (_isProcessingAnimation || _animationQueue.Count == 0) return;
        
        _isProcessingAnimation = true;
        
        while (_animationQueue.Count > 0)
        {
            var anim = _animationQueue.Dequeue();
            
            // Wait for delay
            if (anim.Delay > 0)
            {
                await Task.Delay((int)(anim.Delay * 1000));
            }
            
            // Trigger animation
            TriggerAnimation(anim);
        }
        
        _isProcessingAnimation = false;
    }

    private void TriggerAnimation(AnimationEvent anim)
    {
        GD.Print($"Triggering: {anim.Type} - {anim.Name} (intensity: {anim.Intensity})");
        
        if (anim.Type == "gesture")
        {
            PlayGesture(anim.Name, anim.Intensity);
        }
        else if (anim.Type == "emote")
        {
            SetEmote(anim.Name, anim.Intensity);
        }
    }

    public void PlayGesture(string gestureName, float intensity = 1.0f)
    {
        _currentGesture = gestureName;
        _currentIntensity = intensity;
        
        if (_animationPlayer == null)
        {
            GD.Print($"[No AnimationPlayer] Would play gesture: {gestureName}");
            return;
        }
        
        // Map gesture names to animation names
        var animName = gestureName switch
        {
            "idle" => "Idle",
            "talk" => "Talking",
            "think" => "Thinking",
            "point" => "Pointing",
            "explain" => "Explaining",
            "wave" => "Waving",
            "nod" => "Nodding",
            "shrug" => "Shrugging",
            _ => "Idle"
        };
        
        if (_animationPlayer.HasAnimation(animName))
        {
            _animationPlayer.Play(animName);
            _animationPlayer.SpeedScale = intensity;
        }
        else
        {
            GD.Print($"Animation not found: {animName}, falling back to Idle");
            if (_animationPlayer.HasAnimation("Idle"))
                _animationPlayer.Play("Idle");
        }
    }

    public void SetEmote(string emoteName, float intensity = 1.0f)
    {
        _currentEmote = emoteName;

        // Update hologram color based on emote
        var emoteColor = emoteName switch
        {
            "happy" => new Color(0.4f, 1.0f, 0.6f, 0.9f),      // Warm green
            "excited" => new Color(1.0f, 0.8f, 0.3f, 0.95f),   // Golden
            "thinking" => new Color(0.5f, 0.5f, 1.0f, 0.85f),  // Purple-ish
            "concern" => new Color(0.8f, 0.6f, 0.4f, 0.9f),    // Warm amber
            "love" => new Color(1.0f, 0.5f, 0.7f, 0.95f),      // Pink
            "surprised" => new Color(0.9f, 0.9f, 0.5f, 0.95f), // Bright yellow
            _ => HologramColor  // Default cyan
        };

        // Update material color (applies to all meshes sharing this material)
        if (_hologramMaterial != null)
        {
            _hologramMaterial.SetShaderParameter("hologram_color", emoteColor);
        }

        GD.Print($"Emote set: {emoteName} (color: {emoteColor})");
    }

    #endregion

    #region State Queries

    public string GetCurrentGesture() => _currentGesture;
    public string GetCurrentEmote() => _currentEmote;
    public bool IsAnimating => _isProcessingAnimation || _animationQueue.Count > 0;

    #endregion
}
