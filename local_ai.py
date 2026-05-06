#!/usr/bin/env python3
"""
Simple Local AI Integration for Trading Bot
Free and local - no API keys needed!
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    from transformers import pipeline
    import torch
except ImportError:
    print("Please install: pip install transformers torch")
    sys.exit(1)

class LocalAI:
    def __init__(self):
        self.model = None
        self.load_model()

    def load_model(self):
        """Load the AI model"""
        try:
            print("Loading local AI model...")
            self.model = pipeline(
                "text-generation",
                model="distilgpt2",
                device=0 if torch.cuda.is_available() else -1
            )
            print("✓ Local AI model loaded!")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            self.model = None

    def generate_response(self, prompt, max_tokens=30):
        """Generate AI response for a given prompt"""
        if not self.model:
            return "AI model not loaded"

        try:
            result = self.model(
                prompt,
                max_new_tokens=max_tokens,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True,
                pad_token_id=50256
            )
            response = result[0]['generated_text'][len(prompt):].strip()
            return response if response else "I understand"
        except Exception as e:
            return f"Error: {e}"

# Global AI instance
ai = LocalAI()

def get_ai_response(message):
    """Get AI response for trading bot"""
    prompt = f"Trading analysis: {message}\nResponse:"
    return ai.generate_response(prompt, max_tokens=50)

if __name__ == "__main__":
    # Test the AI
    print("Testing Local AI for Trading Bot...")
    test_message = "What do you think about BTC price movement?"
    response = get_ai_response(test_message)
    print(f"AI Response: {response}")