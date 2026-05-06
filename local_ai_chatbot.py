#!/usr/bin/env python3
"""
Simple Local AI Chatbot using Hugging Face Transformers
Free and local - no API keys needed!
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    from transformers import pipeline
    import torch
    print("✓ Transformers and PyTorch loaded successfully!")
except ImportError as e:
    print(f"❌ Error loading libraries: {e}")
    print("Please install with: pip install transformers torch")
    sys.exit(1)

def create_chatbot():
    """Create a simple conversational AI using a small model"""
    try:
        # Load a very small, fast model for text generation
        print("Loading conversational AI model... (this may take a moment)")
        chatbot = pipeline(
            "text-generation",
            model="distilgpt2",  # Smaller and faster than GPT-2
            device=0 if torch.cuda.is_available() else -1
        )
        print("✓ Model loaded successfully!")
        return chatbot
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        return None

def chat_loop(chatbot):
    """Main chat loop"""
    print("\n🤖 Local AI Chatbot Ready!")
    print("Type 'quit' or 'exit' to end the conversation")
    print("-" * 50)

    while True:
        user_input = input("\nYou: ").strip()

        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("🤖 Goodbye!")
            break

        if not user_input:
            continue

        try:
            # Generate response
            print("🤖 Thinking...", end="", flush=True)

            # Generate response using text generation
            prompt = f"Human: {user_input}\nAssistant:"
            result = chatbot(
                prompt,
                max_new_tokens=50,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True,
                pad_token_id=50256
            )

            full_response = result[0]['generated_text']
            # Extract only the AI's response
            response = full_response[len(prompt):].strip().split('\n')[0]
            if not response or len(response) < 5:
                response = "I understand. Can you tell me more about that?"

            print("\r🤖 AI: " + response)

        except Exception as e:
            print(f"\r❌ Error: {e}")

def main():
    print("🚀 Starting Local AI Chatbot...")

    # Check for CUDA
    if torch.cuda.is_available():
        print("✓ CUDA available - using GPU acceleration")
    else:
        print("ℹ️  CUDA not available - using CPU (may be slower)")

    chatbot = create_chatbot()
    if chatbot:
        chat_loop(chatbot)
    else:
        print("❌ Failed to create chatbot. Please check your installation.")

if __name__ == "__main__":
    main()