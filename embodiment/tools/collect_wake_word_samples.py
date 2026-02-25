#!/usr/bin/env python3
"""
Wake Word Sample Collector

Simple tool for collecting audio samples to train a custom wake word model.
Press SPACE to record, samples are auto-saved with organized naming.

Usage:
    python collect_wake_word_samples.py --wake-word "hey_cass"
    python collect_wake_word_samples.py --wake-word "hey_cass" --negative

Output structure:
    samples/
      hey_cass/
        positive/
          hey_cass_001.wav
          hey_cass_002.wav
          ...
        negative/
          negative_001.wav
          ...
"""

import argparse
import os
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print("ERROR: sounddevice not available. Install with: pip install sounddevice")
    sys.exit(1)

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("ERROR: pygame not available. Install with: pip install pygame")
    sys.exit(1)


class SampleCollector:
    """Collects audio samples for wake word training."""

    def __init__(
        self,
        wake_word: str = "hey_cass",
        output_dir: str = "samples",
        sample_rate: int = 16000,
        duration: float = 2.0,
        negative: bool = False,
    ):
        self.wake_word = wake_word.lower().replace(" ", "_")
        self.output_dir = Path(output_dir)
        self.sample_rate = sample_rate
        self.duration = duration
        self.negative = negative

        # Create output directories
        self.samples_dir = self.output_dir / self.wake_word
        self.positive_dir = self.samples_dir / "positive"
        self.negative_dir = self.samples_dir / "negative"
        self.positive_dir.mkdir(parents=True, exist_ok=True)
        self.negative_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.recording = False
        self.recorded_audio = None
        self.sample_count = self._count_existing_samples()
        self.last_saved_path = None

        # Display
        self.screen = None
        self.font = None
        self.font_small = None
        self.width = 600
        self.height = 400

    def _count_existing_samples(self) -> int:
        """Count existing samples in the target directory."""
        target_dir = self.negative_dir if self.negative else self.positive_dir
        if not target_dir.exists():
            return 0
        return len(list(target_dir.glob("*.wav")))

    def _get_next_filename(self) -> Path:
        """Get the next sample filename."""
        target_dir = self.negative_dir if self.negative else self.positive_dir
        prefix = "negative" if self.negative else self.wake_word

        # Find next available number
        num = 1
        while True:
            filename = f"{prefix}_{num:03d}.wav"
            path = target_dir / filename
            if not path.exists():
                return path
            num += 1

    def _record_sample(self):
        """Record a single audio sample."""
        self.recording = True
        self.recorded_audio = None

        # Calculate number of samples
        num_samples = int(self.sample_rate * self.duration)

        # Record
        print(f"Recording for {self.duration}s...")
        audio = sd.rec(
            num_samples,
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.int16,
        )
        sd.wait()

        self.recorded_audio = audio
        self.recording = False
        print("Recording complete!")

    def _save_sample(self) -> Path:
        """Save the recorded sample to a WAV file."""
        if self.recorded_audio is None:
            return None

        path = self._get_next_filename()

        # Save as WAV
        with wave.open(str(path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(self.recorded_audio.tobytes())

        self.sample_count += 1
        self.last_saved_path = path
        print(f"Saved: {path}")
        return path

    def _play_last_sample(self):
        """Play back the last recorded sample."""
        if self.recorded_audio is not None:
            sd.play(self.recorded_audio, self.sample_rate)
            sd.wait()

    def _delete_last_sample(self):
        """Delete the last saved sample (undo)."""
        if self.last_saved_path and self.last_saved_path.exists():
            self.last_saved_path.unlink()
            print(f"Deleted: {self.last_saved_path}")
            self.sample_count -= 1
            self.last_saved_path = None
            self.recorded_audio = None

    def _draw(self):
        """Draw the UI."""
        # Colors
        bg_color = (20, 20, 30)
        text_color = (200, 200, 220)
        accent_color = (160, 100, 180)
        recording_color = (220, 80, 80)
        success_color = (80, 200, 120)

        self.screen.fill(bg_color)

        # Title
        mode = "NEGATIVE SAMPLES" if self.negative else "POSITIVE SAMPLES"
        title = self.font.render(f"Wake Word: {self.wake_word}", True, accent_color)
        subtitle = self.font_small.render(f"Mode: {mode}", True, text_color)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, 30))
        self.screen.blit(subtitle, (self.width // 2 - subtitle.get_width() // 2, 70))

        # Sample count
        count_text = self.font.render(f"Samples: {self.sample_count}", True, success_color)
        self.screen.blit(count_text, (self.width // 2 - count_text.get_width() // 2, 120))

        # Status
        if self.recording:
            status = self.font.render("RECORDING...", True, recording_color)
            instruction = self.font_small.render(f"Say: \"{self.wake_word.replace('_', ' ')}\"", True, text_color)
        elif self.recorded_audio is not None:
            status = self.font_small.render("Sample recorded!", True, success_color)
            instruction = self.font_small.render("SPACE: record again | P: playback | D: delete | Q: quit", True, text_color)
        else:
            status = self.font_small.render("Ready to record", True, text_color)
            instruction = self.font_small.render("Press SPACE to start recording", True, text_color)

        self.screen.blit(status, (self.width // 2 - status.get_width() // 2, 180))
        self.screen.blit(instruction, (self.width // 2 - instruction.get_width() // 2, 220))

        # Last saved file
        if self.last_saved_path:
            saved_text = self.font_small.render(f"Last: {self.last_saved_path.name}", True, (100, 100, 120))
            self.screen.blit(saved_text, (self.width // 2 - saved_text.get_width() // 2, 280))

        # Instructions at bottom
        if self.negative:
            tip = "Record phrases that should NOT trigger the wake word"
        else:
            tip = "Record the wake word with varied tone, speed, distance"
        tip_text = self.font_small.render(tip, True, (100, 100, 120))
        self.screen.blit(tip_text, (self.width // 2 - tip_text.get_width() // 2, 340))

        # Progress bar (goal: 50 samples minimum)
        goal = 50
        progress = min(1.0, self.sample_count / goal)
        bar_width = 400
        bar_height = 20
        bar_x = (self.width - bar_width) // 2
        bar_y = 300

        # Background
        pygame.draw.rect(self.screen, (40, 40, 50), (bar_x, bar_y, bar_width, bar_height))
        # Fill
        fill_width = int(bar_width * progress)
        fill_color = success_color if progress >= 1.0 else accent_color
        pygame.draw.rect(self.screen, fill_color, (bar_x, bar_y, fill_width, bar_height))
        # Border
        pygame.draw.rect(self.screen, text_color, (bar_x, bar_y, bar_width, bar_height), 1)
        # Label
        progress_label = self.font_small.render(f"{self.sample_count}/{goal} samples", True, text_color)
        self.screen.blit(progress_label, (bar_x + bar_width + 10, bar_y))

        pygame.display.flip()

    def run(self):
        """Main loop."""
        pygame.init()
        pygame.display.set_caption(f"Wake Word Sample Collector - {self.wake_word}")

        self.screen = pygame.display.set_mode((self.width, self.height))
        self.font = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 28)

        clock = pygame.time.Clock()
        running = True

        print(f"\nCollecting {'negative' if self.negative else 'positive'} samples for: {self.wake_word}")
        print(f"Output directory: {self.samples_dir}")
        print(f"Existing samples: {self.sample_count}")
        print("\nControls:")
        print("  SPACE - Record sample")
        print("  P     - Playback last recording")
        print("  D     - Delete last sample")
        print("  Q/ESC - Quit")
        print()

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        running = False

                    elif event.key == pygame.K_SPACE and not self.recording:
                        # Record and save
                        self._draw()  # Show recording state
                        pygame.display.flip()
                        self._record_sample()
                        self._save_sample()

                    elif event.key == pygame.K_p:
                        # Playback
                        self._play_last_sample()

                    elif event.key == pygame.K_d:
                        # Delete last
                        self._delete_last_sample()

            self._draw()
            clock.tick(30)

        pygame.quit()
        print(f"\nDone! Collected {self.sample_count} samples.")
        print(f"Samples saved to: {self.samples_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Collect audio samples for wake word training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect positive samples (the wake word itself)
  python collect_wake_word_samples.py --wake-word "hey_cass"

  # Collect negative samples (similar phrases that shouldn't trigger)
  python collect_wake_word_samples.py --wake-word "hey_cass" --negative

Tips for good samples:
  - Collect 50-100 positive samples minimum
  - Vary your distance from the microphone
  - Vary your speaking speed and tone
  - Include some background noise
  - Get samples from multiple speakers if possible

  For negative samples:
  - "Hey Class", "Hey Cast", "A Cast", "Hey Cat"
  - Random speech, music, silence
  - Similar-sounding phrases
"""
    )
    parser.add_argument(
        "--wake-word", "-w",
        default="hey_cass",
        help="Wake word to collect samples for (default: hey_cass)"
    )
    parser.add_argument(
        "--output", "-o",
        default="samples",
        help="Output directory for samples (default: samples)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=2.0,
        help="Recording duration in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--sample-rate", "-r",
        type=int,
        default=16000,
        help="Sample rate in Hz (default: 16000)"
    )
    parser.add_argument(
        "--negative", "-n",
        action="store_true",
        help="Collect negative samples (phrases that shouldn't trigger)"
    )

    args = parser.parse_args()

    collector = SampleCollector(
        wake_word=args.wake_word,
        output_dir=args.output,
        sample_rate=args.sample_rate,
        duration=args.duration,
        negative=args.negative,
    )
    collector.run()


if __name__ == "__main__":
    main()
