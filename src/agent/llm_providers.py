import os
from abc import ABC, abstractmethod
from typing import Optional

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
    
    def get_usage(self) -> dict:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        try:
            import openai
            self.client = openai.OpenAI(api_key=api_key)
        except ImportError:
            self.client = None
            print("Warning: 'openai' package not installed. Please install it with 'pip install openai'")

    def generate(self, prompt: str) -> str:
        if not self.client:
            return "Error: OpenAI client not initialized (missing package)."
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful Data Operations Agent. You analyze data ingestion reports. You follow the ReAct pattern: Thought, Action, Observation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            
            # Track usage
            if response.usage:
                self.usage["prompt_tokens"] += response.usage.prompt_tokens
                self.usage["completion_tokens"] += response.usage.completion_tokens
                self.usage["total_tokens"] += response.usage.total_tokens
                
            return response.choices[0].message.content
        except Exception as e:
            return f"Error calling OpenAI: {e}"

    def get_usage(self) -> dict:
        return self.usage

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229"):
        self.api_key = api_key
        self.model = model
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            self.client = None
            print("Warning: 'anthropic' package not installed. Please install it with 'pip install anthropic'")

    def generate(self, prompt: str) -> str:
        if not self.client:
            return "Error: Anthropic client not initialized."
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            return f"Error calling Anthropic: {e}"

class GoogleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-pro"):
        self.api_key = api_key
        self.model = model
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.model_instance = genai.GenerativeModel(model)
        except ImportError:
            self.model_instance = None
            print("Warning: 'google-generativeai' package not installed. Please install it with 'pip install google-generativeai'")

    def generate(self, prompt: str) -> str:
        if not self.model_instance:
            return "Error: Google client not initialized."
        try:
            response = self.model_instance.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error calling Google: {e}"

class MockProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        raise NotImplementedError("MockProvider is disabled. Please provide a valid API Key for OpenAI, Anthropic, or Google.")

def get_llm_provider(provider: str, api_key: str, model: str = None) -> LLMProvider:
    if not api_key and provider.lower() != "mock":
         raise ValueError(f"API Key is required for provider '{provider}'")

    if provider.lower() == "openai":
        return OpenAIProvider(api_key, model or "gpt-4-turbo")
    elif provider.lower() == "anthropic":
        return AnthropicProvider(api_key, model or "claude-3-opus-20240229")
    elif provider.lower() == "google":
        return GoogleProvider(api_key, model or "gemini-pro")
    else:
        return MockProvider()
