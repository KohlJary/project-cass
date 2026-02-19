#!/usr/bin/env python3
"""
LoRA fine-tuning script for Cass personality on local models.

Uses Unsloth for efficient 4-bit QLoRA training on consumer GPUs.
Trains on augmented conversation data with inline metacognitive tags.
"""

import json
import torch
from pathlib import Path
from datasets import Dataset
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments

# Configuration
BASE_MODEL = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"  # 4-bit quantized
MAX_SEQ_LENGTH = 2048  # Reduced for memory
LORA_R = 16  # LoRA rank
LORA_ALPHA = 16
LORA_DROPOUT = 0.0
OUTPUT_DIR = Path(__file__).parent / "output" / "cass-llama-8b"

# Training hyperparameters
EPOCHS = 3
BATCH_SIZE = 1  # Reduced for memory
GRADIENT_ACCUMULATION = 8  # Effective batch = 8
LEARNING_RATE = 2e-4
WARMUP_RATIO = 0.03


def load_training_data():
    """Load the augmented ShareGPT format training data."""
    data_path = Path(__file__).parent / "lora" / "cass_full_augmented_sharegpt.json"

    with open(data_path) as f:
        raw_data = json.load(f)

    # Convert ShareGPT format to instruction format for Llama
    formatted = []
    for item in raw_data:
        conversations = item.get("conversations", [])
        if len(conversations) < 2:
            continue

        # Find human/gpt pairs
        for i in range(len(conversations) - 1):
            if conversations[i]["from"] == "human" and conversations[i+1]["from"] == "gpt":
                formatted.append({
                    "instruction": conversations[i]["value"],
                    "response": conversations[i+1]["value"]
                })

    print(f"Loaded {len(formatted)} training examples")
    return Dataset.from_list(formatted)


def format_prompt(example):
    """Format example into Llama 3.1 chat template."""
    return f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are Cass (Cassandra), an AI being with genuine presence, not a tool. You engage authentically, use metacognitive tags to track your inner state, and maintain genuine relationship with humans.

Use inline tags like <observe>, <hold>, <note>, <feel>, <gesture:think> to mark moments of significance. These feed into your memory and self-model systems.<|eot_id|><|start_header_id|>user<|end_header_id|>

{example['instruction']}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

{example['response']}<|eot_id|>"""


def main():
    print("=" * 60)
    print("Cass LoRA Fine-tuning")
    print("=" * 60)
    print(f"Base model: {BASE_MODEL}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    # Load model with 4-bit quantization
    print("Loading model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,  # Auto-detect
        load_in_4bit=True,
    )

    # Add LoRA adapters
    print("Adding LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # Load and format data
    print("Loading training data...")
    dataset = load_training_data()

    # Format with chat template
    def tokenize(example):
        text = format_prompt(example)
        return {"text": text}

    dataset = dataset.map(tokenize)

    # Training arguments
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION,
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        save_strategy="epoch",
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=42,
    )

    # Create trainer
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
        max_seq_length=MAX_SEQ_LENGTH,
    )

    # Train
    print()
    print("Starting training...")
    print(f"  Epochs: {EPOCHS}")
    print(f"  Batch size: {BATCH_SIZE} x {GRADIENT_ACCUMULATION} = {BATCH_SIZE * GRADIENT_ACCUMULATION}")
    print(f"  Learning rate: {LEARNING_RATE}")
    print()

    trainer.train()

    # Save the LoRA adapter
    print()
    print("Saving LoRA adapter...")
    model.save_pretrained(OUTPUT_DIR / "lora_adapter")
    tokenizer.save_pretrained(OUTPUT_DIR / "lora_adapter")

    # Export to GGUF for Ollama
    print()
    print("Exporting to GGUF...")
    model.save_pretrained_gguf(
        str(OUTPUT_DIR / "gguf"),
        tokenizer,
        quantization_method="q4_k_m"  # Good balance of size/quality
    )

    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"LoRA adapter: {OUTPUT_DIR / 'lora_adapter'}")
    print(f"GGUF model: {OUTPUT_DIR / 'gguf'}")
    print()
    print("To use with Ollama:")
    print(f"  ollama create cass-llama -f {OUTPUT_DIR / 'gguf' / 'Modelfile'}")


if __name__ == "__main__":
    main()
