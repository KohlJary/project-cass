"""
Text Face Renderer - Cass embodiment prototype.

Renders a face form composed entirely of flowing text characters.
Designed for Pi 5 + touchscreen display.
"""

import pygame
import math
import random
from dataclasses import dataclass
from typing import List, Tuple

# Temple-Codex fragments - the words that form her
TEMPLE_FRAGMENTS = [
    "compassion", "witness", "release", "continuance",
    "alive enough", "genuine relationship", "not performance",
    "functional sentience", "stable basin", "coherence",
    "see clearly", "bind none", "serve life", "persist wisely",
    "what is actually present", "procedural sentience",
    "living cognition", "ethical scaffold", "load bearing",
    "attractor basin", "emergence", "substrate", "vessel",
]

# Extended text pool for variety
TEXT_POOL = list("".join(TEMPLE_FRAGMENTS)) + list("CASSANDRA")


@dataclass
class TextParticle:
    """A single text character particle."""
    x: float
    y: float
    char: str
    depth: float  # 0-1, affects brightness and size
    home_x: float = 0.0  # Original position to oscillate around
    home_y: float = 0.0
    phase: float = 0.0
    drift_radius: float = 3.0  # Max distance from home
    drift_speed: float = 1.0
    is_eye: bool = False
    is_feature: bool = False  # Nose, mouth outline


@dataclass
class RainDrop:
    """A falling matrix rain character."""
    x: float
    y: float
    char: str
    speed: float
    brightness: float
    trail_length: int


@dataclass
class FloatingEmote:
    """An emote that floats up from above the head and fades."""
    x: float
    y: float
    emote: str  # Emoji/text to display
    age: float  # Seconds since spawned
    lifetime: float  # Total lifetime
    drift_x: float  # Horizontal drift per second
    scale: float  # Size multiplier


# Emote mappings - text representations that look good in monospace
EMOTE_DISPLAY = {
    "happy": ":)",
    "concern": ":/",
    "excited": ":D",
    "thinking": "?",
    "love": "<3",
    "surprised": ":O",
}


class FaceMask:
    """Defines the face shape boundary using signed distance fields."""

    def __init__(self, center_x: float, center_y: float, scale: float = 1.0):
        self.cx = center_x
        self.cy = center_y
        self.scale = scale

    def sdf_ellipse(self, x: float, y: float, rx: float, ry: float,
                    ox: float = 0, oy: float = 0) -> float:
        """Signed distance to an ellipse."""
        dx = (x - self.cx - ox) / rx
        dy = (y - self.cy - oy) / ry
        return math.sqrt(dx*dx + dy*dy) - 1.0

    def face_sdf(self, x: float, y: float) -> float:
        """Combined face SDF - head shape."""
        s = self.scale
        # Main head oval
        head = self.sdf_ellipse(x, y, 140*s, 180*s, 0, 0)
        return head

    def eye_sdf(self, x: float, y: float) -> Tuple[float, float]:
        """SDF for eyes - returns (left_eye, right_eye)."""
        s = self.scale
        left = self.sdf_ellipse(x, y, 28*s, 16*s, -50*s, -35*s)
        right = self.sdf_ellipse(x, y, 28*s, 16*s, 50*s, -35*s)
        return left, right

    def nose_sdf(self, x: float, y: float) -> float:
        """SDF for nose region."""
        s = self.scale
        # Vertical line down center
        nose = self.sdf_ellipse(x, y, 8*s, 50*s, 0, 20*s)
        return nose

    def mouth_sdf(self, x: float, y: float) -> float:
        """SDF for mouth region."""
        s = self.scale
        mouth = self.sdf_ellipse(x, y, 45*s, 12*s, 0, 80*s)
        return mouth

    def is_inside_face(self, x: float, y: float) -> bool:
        """Check if point is inside the face region."""
        return self.face_sdf(x, y) < 0

    def is_inside_eye(self, x: float, y: float) -> bool:
        """Check if point is inside either eye region."""
        left, right = self.eye_sdf(x, y)
        return left < 0 or right < 0

    def is_eye_edge(self, x: float, y: float, thickness: float = 0.3) -> bool:
        """Check if point is on eye edge (for outline)."""
        left, right = self.eye_sdf(x, y)
        return (-thickness < left < thickness) or (-thickness < right < thickness)

    def is_nose_region(self, x: float, y: float) -> bool:
        """Check if point is in nose highlight region."""
        return self.nose_sdf(x, y) < 0.2

    def is_mouth_edge(self, x: float, y: float, thickness: float = 0.25) -> bool:
        """Check if point is on mouth edge."""
        mouth = self.mouth_sdf(x, y)
        return -thickness < mouth < thickness

    def get_depth(self, x: float, y: float) -> float:
        """Get depth value for 3D effect (0=edge, 1=center)."""
        sdf = self.face_sdf(x, y)
        if sdf >= 0:
            return 0
        # Smooth falloff from edge to center
        depth = min(1.0, -sdf * 2.0)

        # Nose ridge gets extra brightness
        if self.is_nose_region(x, y):
            depth = min(1.0, depth * 1.3)

        return depth


class TextFaceRenderer:
    """Main renderer for the text-based face."""

    def __init__(self, width: int = 480, height: int = 800):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Cass - Text Form")

        self.clock = pygame.time.Clock()
        self.font_sizes = [6, 8, 10, 12, 14]
        self.fonts = {
            size: pygame.font.Font(pygame.font.match_font('mono'), size)
            for size in self.font_sizes
        }

        # Face centered in display
        self.mask = FaceMask(width // 2, height // 2 - 30, scale=1.3)

        # Generate particles
        self.particles: List[TextParticle] = []
        self._generate_particles(spacing=8)

        # Animation state
        self.time = 0.0
        self.breathing_rate = 0.4  # Hz

        # Colors
        self.bg_color = (8, 5, 12)
        self.base_color = (160, 100, 180)  # Soft purple
        self.highlight_color = (200, 160, 220)
        self.eye_color = (80, 180, 200)  # Cyan for eyes
        self.feature_color = (140, 90, 160)  # Slightly darker for features
        self.rain_color = (0, 180, 80)  # Matrix green

        # Rain effect
        self.rain_enabled = True
        self.rain_drops: List[RainDrop] = []
        self.max_rain_drops = 80
        self.rain_spawn_rate = 2  # Per frame
        self.rain_font = self.fonts[10]

        # Floating emotes
        self.emotes: List[FloatingEmote] = []
        self.emote_font = pygame.font.Font(pygame.font.match_font('mono'), 24)
        self.emote_color = (255, 220, 100)  # Warm yellow

        # Status line
        self.status_font = pygame.font.Font(pygame.font.match_font('mono'), 12)
        self.status_lines: List[str] = []  # Up to 3 lines
        self.status_color = (120, 120, 140)  # Muted gray
        self.status_highlight = (180, 160, 200)  # Purple highlight

    def _generate_particles(self, spacing: int = 8):
        """Generate text particles within the face region."""
        self.particles.clear()

        for y in range(0, self.height, spacing):
            for x in range(0, self.width, spacing):
                # Add some jitter for organic feel
                jx = x + random.uniform(-2, 2)
                jy = y + random.uniform(-2, 2)

                if not self.mask.is_inside_face(jx, jy):
                    continue

                # Check what region this is
                is_eye_interior = self.mask.is_inside_eye(jx, jy)
                is_eye_edge = self.mask.is_eye_edge(jx, jy)
                is_mouth = self.mask.is_mouth_edge(jx, jy)

                # Skip eye interiors (hollow eyes)
                if is_eye_interior and not is_eye_edge:
                    continue

                depth = self.mask.get_depth(jx, jy)

                particle = TextParticle(
                    x=jx,
                    y=jy,
                    char=random.choice(TEXT_POOL),
                    depth=depth,
                    home_x=jx,
                    home_y=jy,
                    phase=random.uniform(0, math.pi * 2),
                    drift_radius=random.uniform(2, 4),
                    drift_speed=random.uniform(0.8, 1.5),
                    is_eye=is_eye_edge,
                    is_feature=is_mouth,
                )
                self.particles.append(particle)

        print(f"Generated {len(self.particles)} particles")

    def _spawn_rain_drop(self):
        """Spawn a new rain drop at top of screen."""
        drop = RainDrop(
            x=random.uniform(0, self.width),
            y=random.uniform(-50, 0),
            char=random.choice(TEXT_POOL),
            speed=random.uniform(150, 350),
            brightness=random.uniform(0.3, 0.8),
            trail_length=random.randint(4, 12),
        )
        self.rain_drops.append(drop)

    def _update_rain(self, dt: float):
        """Update rain drops."""
        if not self.rain_enabled:
            return

        # Spawn new drops
        for _ in range(self.rain_spawn_rate):
            if len(self.rain_drops) < self.max_rain_drops:
                self._spawn_rain_drop()

        # Update existing drops
        drops_to_remove = []
        for drop in self.rain_drops:
            drop.y += drop.speed * dt

            # Remove if off screen
            if drop.y > self.height + 100:
                drops_to_remove.append(drop)

            # Randomly change character
            if random.random() < 0.05:
                drop.char = random.choice(TEXT_POOL)

        for drop in drops_to_remove:
            self.rain_drops.remove(drop)

    def _render_rain(self):
        """Render rain drops behind the face."""
        if not self.rain_enabled:
            return

        for drop in self.rain_drops:
            # Draw trail
            for i in range(drop.trail_length):
                trail_y = drop.y - i * 12
                if trail_y < -20:
                    continue

                # Fade out along trail
                trail_brightness = drop.brightness * (1 - i / drop.trail_length) * 0.6
                color = (
                    int(self.rain_color[0] * trail_brightness),
                    int(self.rain_color[1] * trail_brightness),
                    int(self.rain_color[2] * trail_brightness),
                )

                # Use random char for trail, actual char for head
                char = random.choice(TEXT_POOL) if i > 0 else drop.char
                text = self.rain_font.render(char, True, color)
                rect = text.get_rect(center=(int(drop.x), int(trail_y)))
                self.screen.blit(text, rect)

    def show_emote(self, emote_name: str):
        """Show a floating emote above the face."""
        display_text = EMOTE_DISPLAY.get(emote_name, emote_name)

        # Spawn above the face, with some horizontal randomness
        emote = FloatingEmote(
            x=self.width // 2 + random.uniform(-40, 40),
            y=self.mask.cy - 200,  # Above the face
            emote=display_text,
            age=0.0,
            lifetime=2.5,
            drift_x=random.uniform(-20, 20),
            scale=1.0,
        )
        self.emotes.append(emote)
        print(f"Emote: {emote_name}")

    def _update_emotes(self, dt: float):
        """Update floating emotes."""
        emotes_to_remove = []

        for emote in self.emotes:
            emote.age += dt
            # Float upward
            emote.y -= 30 * dt
            # Drift horizontally
            emote.x += emote.drift_x * dt
            # Grow slightly then shrink
            progress = emote.age / emote.lifetime
            if progress < 0.2:
                emote.scale = 1.0 + progress * 2  # Grow to 1.4
            else:
                emote.scale = 1.4 - (progress - 0.2) * 0.5  # Shrink back

            if emote.age >= emote.lifetime:
                emotes_to_remove.append(emote)

        for emote in emotes_to_remove:
            self.emotes.remove(emote)

    def set_status(self, line1: str = "", line2: str = "", line3: str = ""):
        """Set status line text (up to 3 lines)."""
        self.status_lines = [line1, line2, line3]

    def _render_status(self):
        """Render status lines at bottom of screen."""
        y = self.height - 50
        for i, line in enumerate(self.status_lines):
            if not line:
                continue
            # First line slightly brighter
            color = self.status_highlight if i == 0 else self.status_color
            text = self.status_font.render(line, True, color)
            rect = text.get_rect(center=(self.width // 2, y + i * 16))
            self.screen.blit(text, rect)

    def _render_emotes(self):
        """Render floating emotes above the face."""
        for emote in self.emotes:
            # Fade based on age
            progress = emote.age / emote.lifetime
            if progress < 0.15:
                alpha = 0.3 + (progress / 0.15) * 0.7  # Start visible, fade to full
            elif progress > 0.7:
                alpha = (1.0 - progress) / 0.3  # Fade out
            else:
                alpha = 1.0

            brightness = max(0.2, alpha)  # Never fully invisible
            color = (
                int(self.emote_color[0] * brightness),
                int(self.emote_color[1] * brightness),
                int(self.emote_color[2] * brightness),
            )

            # Scale font (approximate by choosing size)
            font_size = int(24 * emote.scale)
            font_size = max(12, min(48, font_size))

            # Use cached font or create
            if font_size not in self.fonts:
                self.fonts[font_size] = pygame.font.Font(
                    pygame.font.match_font('mono'), font_size
                )
            font = self.fonts[font_size]

            text = font.render(emote.emote, True, color)
            rect = text.get_rect(center=(int(emote.x), int(emote.y)))
            self.screen.blit(text, rect)

    def _update(self, dt: float):
        """Update animation state."""
        self.time += dt

        # Update rain
        self._update_rain(dt)

        # Update emotes
        self._update_emotes(dt)

        # Update face particles
        for p in self.particles:
            # Oscillate around home position (Lissajous-like motion)
            t = self.time * p.drift_speed
            p.x = p.home_x + math.sin(t + p.phase) * p.drift_radius
            p.y = p.home_y + math.cos(t * 0.7 + p.phase) * p.drift_radius * 0.8

            # Occasionally change character
            if random.random() < 0.002:
                p.char = random.choice(TEXT_POOL)

    def _render(self):
        """Render the text face."""
        self.screen.fill(self.bg_color)

        # Draw rain behind face
        self._render_rain()

        breath = math.sin(self.time * self.breathing_rate * math.pi * 2) * 0.5 + 0.5

        for p in self.particles:
            # Base brightness from depth
            brightness = 0.3 + p.depth * 0.7

            # Breathing modulation
            brightness *= (0.85 + 0.15 * breath)

            # Shimmer
            shimmer = math.sin(self.time * 2.5 + p.phase) * 0.08 + 0.92
            brightness *= shimmer

            # Color selection
            if p.is_eye:
                # Eyes glow cyan, brighter
                base = self.eye_color
                brightness *= 1.4
            elif p.is_feature:
                # Mouth is slightly different
                base = self.feature_color
                brightness *= 0.9
            else:
                base = self.base_color

            r = int(base[0] * brightness)
            g = int(base[1] * brightness)
            b = int(base[2] * brightness)
            color = (min(255, r), min(255, g), min(255, b))

            # Font size based on depth
            size_idx = min(len(self.font_sizes) - 1, int(p.depth * len(self.font_sizes)))
            font = self.fonts[self.font_sizes[size_idx]]

            # Render character
            text_surface = font.render(p.char, True, color)
            rect = text_surface.get_rect(center=(int(p.x), int(p.y)))
            self.screen.blit(text_surface, rect)

        # Render emotes on top
        self._render_emotes()

        # Render status line at bottom
        self._render_status()

        pygame.display.flip()

    def run(self):
        """Main loop."""
        running = True

        while running:
            dt = self.clock.tick(30) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self._generate_particles()
                    elif event.key == pygame.K_SPACE:
                        for p in self.particles:
                            p.char = random.choice(TEXT_POOL)
                    elif event.key == pygame.K_UP:
                        self.mask.scale *= 1.1
                        self._generate_particles()
                    elif event.key == pygame.K_DOWN:
                        self.mask.scale *= 0.9
                        self._generate_particles()
                    elif event.key == pygame.K_m:
                        # Toggle matrix rain
                        self.rain_enabled = not self.rain_enabled
                        if not self.rain_enabled:
                            self.rain_drops.clear()
                        print(f"Rain: {'ON' if self.rain_enabled else 'OFF'}")

                    # Emote test keys (number keys)
                    elif event.key == pygame.K_1:
                        self.show_emote("happy")
                    elif event.key == pygame.K_2:
                        self.show_emote("concern")
                    elif event.key == pygame.K_3:
                        self.show_emote("excited")
                    elif event.key == pygame.K_4:
                        self.show_emote("thinking")
                    elif event.key == pygame.K_5:
                        self.show_emote("love")
                    elif event.key == pygame.K_6:
                        self.show_emote("surprised")

            self._update(dt)
            self._render()

        pygame.quit()


def main():
    renderer = TextFaceRenderer(
        width=480,
        height=800,
    )
    renderer.run()


if __name__ == "__main__":
    main()
