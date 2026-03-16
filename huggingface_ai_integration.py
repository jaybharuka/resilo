"""
Hugging Face AI Integration for AIOps Chatbot
Free AI models for enhanced system diagnostics and user interaction
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import warnings
warnings.filterwarnings("ignore")

# Hugging Face imports
from transformers import (
    pipeline, 
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    AutoModelForQuestionAnswering,
    AutoModelForCausalLM
)
import torch

class HuggingFaceAIEngine:
    """
    Free Hugging Face AI integration for AIOps
    Provides sentiment analysis, text classification, Q&A, and more
    """
    
    def __init__(self):
        self.models = {}
        self.pipelines = {}
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🤗 Initializing Hugging Face AI Engine on {self.device}")
        
        # Initialize free models
        self.initialize_models()
    
    def initialize_models(self):
        """Initialize free Hugging Face models"""
        try:
            print("📥 Loading Hugging Face models...")
            
            # 1. Sentiment Analysis (for understanding user emotions)
            print("  🎭 Loading sentiment analysis model...")
            self.pipelines['sentiment'] = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                device=0 if self.device == "cuda" else -1
            )
            
            # 2. Text Classification (for categorizing system issues)
            print("  📊 Loading text classification model...")
            self.pipelines['classification'] = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=0 if self.device == "cuda" else -1
            )
            
            # 3. Question Answering (for intelligent responses)
            print("  ❓ Loading question answering model...")
            self.pipelines['qa'] = pipeline(
                "question-answering",
                model="distilbert-base-cased-distilled-squad",
                device=0 if self.device == "cuda" else -1
            )
            
            # 4. Text Summarization (for log analysis)
            print("  📝 Loading text summarization model...")
            self.pipelines['summarization'] = pipeline(
                "summarization",
                model="facebook/bart-large-cnn",
                device=0 if self.device == "cuda" else -1
            )
            
            # 5. Text Generation (for creative responses)
            print("  ✍️  Loading text generation model...")
            self.pipelines['generation'] = pipeline(
                "text-generation",
                model="microsoft/DialoGPT-medium",
                device=0 if self.device == "cuda" else -1
            )
            
            print("✅ All Hugging Face models loaded successfully!")
            
        except Exception as e:
            print(f"⚠️ Error loading models: {e}")
            print("📶 Using lightweight fallback models...")
            self.initialize_fallback_models()
    
    def initialize_fallback_models(self):
        """Initialize lightweight models as fallback"""
        try:
            # Use smaller, faster models for demo purposes
            self.pipelines['sentiment'] = pipeline("sentiment-analysis")
            self.pipelines['summarization'] = pipeline("summarization")
            self.pipelines['qa'] = pipeline("question-answering")
            print("✅ Fallback models loaded successfully!")
        except Exception as e:
            print(f"❌ Error loading fallback models: {e}")
    
    def analyze_user_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze user sentiment to understand their emotional state
        Helps the chatbot respond more empathetically
        """
        try:
            if 'sentiment' not in self.pipelines:
                return {"sentiment": "neutral", "confidence": 0.5, "emotion": "calm"}
            
            result = self.pipelines['sentiment'](text)
            
            # Map sentiment to user emotions
            sentiment_map = {
                "POSITIVE": {"emotion": "satisfied", "response_tone": "encouraging"},
                "NEGATIVE": {"emotion": "frustrated", "response_tone": "helpful"},
                "NEUTRAL": {"emotion": "calm", "response_tone": "informative"}
            }
            
            sentiment = result[0]['label'] if isinstance(result, list) else result['label']
            confidence = result[0]['score'] if isinstance(result, list) else result['score']
            
            emotion_data = sentiment_map.get(sentiment, {"emotion": "calm", "response_tone": "informative"})
            
            return {
                "sentiment": sentiment.lower(),
                "confidence": round(confidence, 3),
                "emotion": emotion_data["emotion"],
                "response_tone": emotion_data["response_tone"],
                "raw_result": result
            }
            
        except Exception as e:
            print(f"Error in sentiment analysis: {e}")
            return {"sentiment": "neutral", "confidence": 0.5, "emotion": "calm"}
    
    def classify_system_issue(self, user_message: str, system_data: Dict) -> Dict[str, Any]:
        """
        Classify the type of system issue using zero-shot classification
        Helps route the user to the right solution
        """
        try:
            if 'classification' not in self.pipelines:
                return self.fallback_classification(user_message, system_data)
            
            # Define issue categories
            issue_categories = [
                "performance problems",
                "memory issues", 
                "disk storage problems",
                "network connectivity",
                "software crashes",
                "hardware problems",
                "security concerns",
                "general system health",
                "application errors"
            ]
            
            result = self.pipelines['classification'](user_message, issue_categories)
            
            # Get the most likely category
            top_category = result['labels'][0]
            confidence = result['scores'][0]
            
            # Add contextual information based on system data
            context = self.add_system_context(top_category, system_data)
            
            return {
                "primary_category": top_category,
                "confidence": round(confidence, 3),
                "all_categories": list(zip(result['labels'][:3], result['scores'][:3])),
                "context": context,
                "suggested_actions": self.get_suggested_actions(top_category)
            }
            
        except Exception as e:
            print(f"Error in issue classification: {e}")
            return self.fallback_classification(user_message, system_data)
    
    def fallback_classification(self, user_message: str, system_data: Dict) -> Dict[str, Any]:
        """Fallback classification using keyword matching"""
        keywords_map = {
            "performance problems": ["slow", "lag", "performance", "speed"],
            "memory issues": ["memory", "ram", "out of memory"],
            "disk storage problems": ["disk", "storage", "space", "full"],
            "network connectivity": ["network", "internet", "connection"],
            "software crashes": ["crash", "error", "bug", "freeze"]
        }
        
        user_lower = user_message.lower()
        for category, keywords in keywords_map.items():
            if any(keyword in user_lower for keyword in keywords):
                return {
                    "primary_category": category,
                    "confidence": 0.8,
                    "context": f"Detected {category} based on keywords",
                    "suggested_actions": self.get_suggested_actions(category)
                }
        
        return {
            "primary_category": "general system health",
            "confidence": 0.5,
            "context": "General inquiry",
            "suggested_actions": ["Run system diagnostics"]
        }
    
    def intelligent_qa_response(self, question: str, context: str) -> Dict[str, Any]:
        """
        Use Q&A model to provide intelligent responses based on system context
        """
        try:
            if 'qa' not in self.pipelines:
                return {"answer": "I'll help you analyze that issue.", "confidence": 0.5}
            
            # Prepare context with system information
            formatted_context = f"""
System Information: {context}

The user is asking about system issues. Provide helpful technical guidance based on the system data provided.
"""
            
            result = self.pipelines['qa'](
                question=question,
                context=formatted_context
            )
            
            return {
                "answer": result['answer'],
                "confidence": round(result['score'], 3),
                "context_used": formatted_context[:200] + "..."
            }
            
        except Exception as e:
            print(f"Error in Q&A: {e}")
            return {"answer": "Let me analyze your system to help you with that.", "confidence": 0.5}
    
    def summarize_system_logs(self, log_text: str, max_length: int = 100) -> Dict[str, Any]:
        """
        Summarize lengthy system logs for easier understanding
        """
        try:
            if 'summarization' not in self.pipelines or len(log_text) < 100:
                return {"summary": log_text[:200], "method": "truncation"}
            
            # Prepare log text for summarization
            formatted_text = f"System Log Analysis: {log_text}"
            
            result = self.pipelines['summarization'](
                formatted_text,
                max_length=max_length,
                min_length=30,
                do_sample=False
            )
            
            return {
                "summary": result[0]['summary_text'],
                "original_length": len(log_text),
                "compressed_ratio": round(len(result[0]['summary_text']) / len(log_text), 2),
                "method": "ai_summarization"
            }
            
        except Exception as e:
            print(f"Error in summarization: {e}")
            return {"summary": log_text[:200] + "...", "method": "fallback_truncation"}
    
    def generate_empathetic_response(self, user_emotion: str, base_response: str) -> str:
        """
        Generate more empathetic responses based on user emotion
        """
        emotion_templates = {
            "frustrated": [
                "I understand this is frustrating. Let me help you resolve this quickly. ",
                "I can see this is causing you stress. Here's what we can do: ",
                "Don't worry, I'm here to help fix this issue. "
            ],
            "satisfied": [
                "Great! I'm glad to help you with this. ",
                "Perfect! Let's take a look at your system. ",
                "Excellent! Here's what I found: "
            ],
            "calm": [
                "Let me analyze this for you. ",
                "I'll help you understand what's happening. ",
                "Here's my analysis: "
            ]
        }
        
        templates = emotion_templates.get(user_emotion, emotion_templates["calm"])
        import random
        empathy_prefix = random.choice(templates)
        
        return empathy_prefix + base_response
    
    def add_system_context(self, category: str, system_data: Dict) -> str:
        """Add relevant system context based on issue category"""
        cpu_usage = system_data.get('cpu', {}).get('usage_percent', 0)
        memory_usage = system_data.get('memory', {}).get('percent', 0)
        disk_usage = system_data.get('disk', {}).get('percent', 0)
        
        context_map = {
            "performance problems": f"Current system load: CPU {cpu_usage}%, Memory {memory_usage}%",
            "memory issues": f"Memory usage: {memory_usage}% of available RAM",
            "disk storage problems": f"Disk usage: {disk_usage}% of total storage",
            "network connectivity": "Network status and connectivity analysis needed",
            "general system health": f"Overall system: CPU {cpu_usage}%, RAM {memory_usage}%, Disk {disk_usage}%"
        }
        
        return context_map.get(category, "System analysis required")
    
    def get_suggested_actions(self, category: str) -> List[str]:
        """Get suggested actions based on issue category"""
        actions_map = {
            "performance problems": [
                "Check CPU and memory usage",
                "Close unnecessary applications",
                "Run performance diagnostics"
            ],
            "memory issues": [
                "Close memory-intensive applications",
                "Restart applications with memory leaks",
                "Consider adding more RAM"
            ],
            "disk storage problems": [
                "Clean temporary files",
                "Remove unnecessary downloads",
                "Move files to external storage"
            ],
            "network connectivity": [
                "Check network cable connections",
                "Restart network adapter",
                "Run network diagnostics"
            ],
            "software crashes": [
                "Check application logs",
                "Update problematic software",
                "Run system file checker"
            ]
        }
        
        return actions_map.get(category, ["Run general system diagnostics"])
    
    def enhance_chatbot_response(self, user_message: str, base_response: str, system_data: Dict) -> Dict[str, Any]:
        """
        Main function to enhance chatbot responses using all AI models
        """
        try:
            # 1. Analyze user sentiment
            sentiment_analysis = self.analyze_user_sentiment(user_message)
            
            # 2. Classify the system issue
            issue_classification = self.classify_system_issue(user_message, system_data)
            
            # 3. Generate empathetic response
            empathetic_response = self.generate_empathetic_response(
                sentiment_analysis['emotion'], 
                base_response
            )
            
            # 4. Add intelligent Q&A if needed
            if len(user_message) > 20:  # For detailed questions
                qa_result = self.intelligent_qa_response(
                    user_message, 
                    json.dumps(system_data)
                )
                if qa_result['confidence'] > 0.7:
                    empathetic_response += f"\n\n🤖 <strong>AI Insight:</strong> {qa_result['answer']}"
            
            return {
                "enhanced_response": empathetic_response,
                "sentiment": sentiment_analysis,
                "issue_classification": issue_classification,
                "ai_confidence": issue_classification['confidence'],
                "suggested_actions": issue_classification['suggested_actions'],
                "processing_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error in response enhancement: {e}")
            return {
                "enhanced_response": base_response,
                "error": str(e),
                "fallback": True
            }

# Global instance
huggingface_ai = None

def initialize_huggingface_ai():
    """Initialize the Hugging Face AI engine"""
    global huggingface_ai
    if huggingface_ai is None:
        huggingface_ai = HuggingFaceAIEngine()
    return huggingface_ai

def enhance_response_with_ai(user_message: str, base_response: str, system_data: Dict) -> Dict[str, Any]:
    """
    Main function to enhance responses using Hugging Face AI
    """
    ai_engine = initialize_huggingface_ai()
    return ai_engine.enhance_chatbot_response(user_message, base_response, system_data)

# Demo function
def demo_huggingface_integration():
    """Demonstrate Hugging Face integration"""
    print("🤗 Hugging Face AI Integration Demo")
    print("=" * 50)
    
    # Initialize AI engine
    ai_engine = initialize_huggingface_ai()
    
    # Demo data
    sample_messages = [
        "My computer is so slow, I'm really frustrated!",
        "Can you check my memory usage?",
        "Everything seems to be running fine today",
        "I'm getting weird error messages"
    ]
    
    sample_system_data = {
        "cpu": {"usage_percent": 75},
        "memory": {"percent": 88},
        "disk": {"percent": 65}
    }
    
    for message in sample_messages:
        print(f"\n💬 User: {message}")
        
        # Analyze sentiment
        sentiment = ai_engine.analyze_user_sentiment(message)
        print(f"🎭 Sentiment: {sentiment['sentiment']} ({sentiment['confidence']:.2f}) - {sentiment['emotion']}")
        
        # Classify issue
        classification = ai_engine.classify_system_issue(message, sample_system_data)
        print(f"📊 Issue Type: {classification['primary_category']} ({classification['confidence']:.2f})")
        
        # Enhanced response
        base_response = "Let me analyze your system for you."
        enhanced = ai_engine.enhance_chatbot_response(message, base_response, sample_system_data)
        print(f"🤖 Enhanced Response: {enhanced['enhanced_response']}")
        
        print("-" * 50)

if __name__ == "__main__":
    demo_huggingface_integration()