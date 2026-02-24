"""
Matrix Rain Face - Text rains down and coalesces into face shape.

Characters fall from top of screen and "stick" when they hit
the face boundary, building up the form over time.
"""

import pygame
import math
import random
from dataclasses import dataclass
from typing import List, Optional

# Temple-Codex fragments
TEMPLE_FRAGMENTS = [
    "compassion", "witness", "release", "continuance",
    "alive enough", "genuine relationship", "not performance",
    "functional sentience", "stable basin", "coherence",
    "see clearly", "bind none", "serve life", "persist wisely",
    "what is actually present", "procedural sentience",
    "living cognition", "ethical scaffold", "load bearing",
    "attractor basin", "emergence", "substrate", "vessel",
]

TEXT_POOL = list("".join(TEMPLE_FRAGMENTS)) + list("CASSANDRA")


@dataclass
class RainDrop:
    """A falling text character."""
    x: float
    y: float
    char: str
    speed: float
    brightness: float
    trail_length: int
    stuck: bool = False
    stuck_brightness: float = 0.0
    fade_in: float = 0.0  # For stuck particles fading in


@dataclass
class StuckParticle:
    """A particle that has stuck to the face."""
    x: float
    y: float
    char: str
    brightness: float
    phase: float
    depth: float


class FaceMask:
    """Face shape definition."""

    def __init__(self, center_x: float, center_y: float, scale: float = 1.0):
        self.cx = center_x
        self.cy = center_y
        self.scale = scale

    def sdf_ellipse(self, x: float, y: float, rx: float, ry: float,
                    ox: float = 0, oy: float = 0) -> float:
        dx = (x - self.cx - ox) / rx
        dy = (y - self.cy - oy) / ry
        return math.sqrt(dx*dx + dy*dy) - 1.0

    def face_sdf(self, x: float, y: float) -> float:
        s = self.scale
        return self.sdf_ellipse(x, y, 140*s, 180*s, 0, 0)

    def eye_sdf(self, x: float, y: float) -> tuple:
        s = self.scale
        left = self.sdf_ellipse(x, y, 28*s, 16*s, -50*s, -35*s)
        right = self.sdf_ellipse(x, y, 28*s, 16*s, 50*s, -35*s)
        return left, right

    def is_inside_face(self, x: float, y: float) -> bool:
        return self.face_sdf(x, y) < 0

    def is_inside_eye(self, x: float, y: float) -> bool:
        left, right = self.eye_sdf(x, y)
        return left < 0 or right < 0

    def is_eye_edge(self, x: float, y: float, thickness: float = 0.3) -> bool:
        left, right = self.eye_sdf(x, y)
        return (-thickness < left < thickness) or (-thickness < right < thickness)

    def get_depth(self, x: float, y: float) -> float:
        sdf = self.face_sdf(x, y)
        if sdf >= 0:
            return 0
        return min(1.0, -sdf * 2.0)


class MatrixFaceRenderer:
    """Matrix rain that forms a face."""

    def __init__(self, width: int = 480, height: int = 800):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Cass - Matrix Form")

        self.clock = pygame.time.Clock()

        # Fonts
        self.font_sizes = [10, 12, 14, 16]
        self.fonts = {
            size: pygame.font.Font(pygame.font.match_font('mono'), size)
            for size in self.font_sizes
        }
        self.rain_font = self.fonts[12]

        # Face mask
        self.mask = FaceMask(width // 2, height // 2 - 30, scale=1.3)

        # Rain drops
        self.drops: List[RainDrop] = []
        self.stuck_particles: List[StuckParticle] = []
        self.max_drops = 150
        self.spawn_rate = 3  # Drops per frame

        # Grid to track where particles have stuck (prevents overlap)
        self.grid_size = 8
        self.stuck_grid = set()

        # Animation
        self.time = 0.0
        self.face_complete = False

        # Colors
        self.bg_color = (5, 5, 10)
        self.rain_color = (0, 255, 100)  # Matrix green
        self.face_color = (180, 120, 220)  # Purple for face
        self.eye_color = (100, 220, 255)  # Cyan for eyes

    def _spawn_drop(self):
        """Spawn a new rain drop at top of screen."""
        drop = RainDrop(
            x=random.uniform(0, self.width),
            y=random.uniform(-50, 0),
            char=random.choice(TEXT_POOL),
            speed=random.uniform(200, 400),
            brightness=random.uniform(0.5, 1.0),
            trail_length=random.randint(3, 8),
        )
        self.drops.append(drop)

    def _grid_key(self, x: float, y: float) -> tuple:
        """Get grid cell for position."""
        return (int(x // self.grid_size), int(y // self.grid_size))

    def _update(self, dt: float):
        """Update rain and stuck particles."""
        self.time += dt

        # Spawn new drops
        for _ in range(self.spawn_rate):
            if len(self.drops) < self.max_drops:
                self._spawn_drop()

        # Update drops
        drops_to_remove = []
        for drop in self.drops:
            if drop.stuck:
                drops_to_remove.append(drop)
                continue

            # Move down
            drop.y += drop.speed * dt

            # Check if hit face boundary
            if self.mask.is_inside_face(drop.x, drop.y):
                # Check if this grid cell is already occupied
                grid_key = self._grid_key(drop.x, drop.y)

                # Don't stick inside eyes (except edges)
                is_eye_interior = self.mask.is_inside_eye(drop.x, drop.y)
                is_eye_edge = self.mask.is_eye_edge(drop.x, drop.y)

                if grid_key not in self.stuck_grid and not (is_eye_interior and not is_eye_edge):
                    # Stick!
                    self.stuck_grid.add(grid_key)

                    depth = self.mask.get_depth(drop.x, drop.y)

                    self.stuck_particles.append(StuckParticle(
                        x=drop.x,
                        y=drop.y,
                        char=drop.char,
                        brightness=0.0,  # Fade in
                        phase=random.uniform(0, math.pi * 2),
                        depth=depth,
                    ))
                    drop.stuck = True
                # If grid occupied, drop passes through

            # Remove if off screen
            if drop.y > self.height + 50:
                drops_to_remove.append(drop)

            # Randomly change character (matrix effect)
            if random.random() < 0.1:
                drop.char = random.choice(TEXT_POOL)

        for drop in drops_to_remove:
            if drop in self.drops:
                self.drops.remove(drop)

        # Update stuck particles (fade in, shimmer)
        for p in self.stuck_particles:
            # Fade in
            if p.brightness < 1.0:
                p.brightness = min(1.0, p.brightness + dt * 2)

    def _render(self):
        """Render the scene."""
        self.screen.fill(self.bg_color)

        # Draw rain drops with trails
        for drop in self.drops:
            if drop.stuck:
                continue

            # Trail
            for i in range(drop.trail_length):
                trail_y = drop.y - i * 15
                if trail_y < 0:
                    continue

                trail_brightness = drop.brightness * (1 - i / drop.trail_length) * 0.5
                color = (
                    int(self.rain_color[0] * trail_brightness),
                    int(self.rain_color[1] * trail_brightness),
                    int(self.rain_color[2] * trail_brightness),
                )

                char = random.choice(TEXT_POOL) if i > 0 else drop.char
                text = self.rain_font.render(char, True, color)
                rect = text.get_rect(center=(int(drop.x), int(trail_y)))
                self.screen.blit(text, rect)

            # Head of drop (brightest)
            color = (
                int(self.rain_color[0] * drop.brightness),
                int(self.rain_color[1] * drop.brightness),
                int(self.rain_color[2] * drop.brightness),
            )
            text = self.rain_font.render(drop.char, True, color)
            rect = text.get_rect(center=(int(drop.x), int(drop.y)))
            self.screen.blit(text, rect)

        # Draw stuck particles (the face)
        breath = math.sin(self.time * 0.4 * math.pi * 2) * 0.5 + 0.5

        for p in self.stuck_particles:
            # Shimmer
            shimmer = math.sin(self.time * 2 + p.phase) * 0.1 + 0.9
            brightness = p.brightness * (0.7 + 0.3 * p.depth) * shimmer * (0.85 + 0.15 * breath)

            # Check if eye edge
            is_eye = self.mask.is_eye_edge(p.x, p.y)

            if is_eye:
                base = self.eye_color
                brightness *= 1.3
            else:
                base = self.face_color

            color = (
                min(255, int(base[0] * brightness)),
                min(255, int(base[1] * brightness)),
                min(255, int(base[2] * brightness)),
            )

            size_idx = min(len(self.font_sizes) - 1, int(p.depth * len(self.font_sizes)))
            font = self.fonts[self.font_sizes[size_idx]]

            text = font.render(p.char, True, color)
            rect = text.get_rect(center=(int(p.x), int(p.y)))
            self.screen.blit(text, rect)

        pygame.display.flip()

    def reset(self):
        """Clear stuck particles and restart rain."""
        self.stuck_particles.clear()
        self.stuck_grid.clear()
        self.drops.clear()

    def run(self):
        """Main loop."""
        running = True

        while running:
            dt = self.clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self.reset()
                    elif event.key == pygame.K_SPACE:
                        # Burst of drops
                        for _ in range(50):
                            self._spawn_drop()
                    elif event.key == pygame.K_UP:
                        self.spawn_rate = min(10, self.spawn_rate + 1)
                        print(f"Spawn rate: {self.spawn_rate}")
                    elif event.key == pygame.K_DOWN:
                        self.spawn_rate = max(1, self.spawn_rate - 1)
                        print(f"Spawn rate: {self.spawn_rate}")

            self._update(dt)
            self._render()

        pygame.quit()


def main():
    renderer = MatrixFaceRenderer(
        width=480,
        height=800,
    )
    renderer.run()


if __name__ == "__main__":
    main()
