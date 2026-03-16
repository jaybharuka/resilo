"""
Enhanced Social Bots for Slack & Discord
Interactive bots for casual conversation and team interaction
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiohttp
import re
from dataclasses import dataclass
from enum import Enum
import random

# Mock Discord/Slack API classes for demonstration
class BotPlatform(Enum):
    SLACK = "slack"
    DISCORD = "discord"
    TEAMS = "teams"

@dataclass
class Message:
    id: str
    content: str
    author_id: str
    author_name: str
    channel_id: str
    timestamp: datetime
    platform: BotPlatform
    is_direct_message: bool = False
    mentions_bot: bool = False

@dataclass
class User:
    id: str
    name: str
    platform: BotPlatform
    is_online: bool = True
    last_interaction: Optional[datetime] = None

class ConversationContext:
    def __init__(self):
        self.topic: Optional[str] = None
        self.mood: str = "neutral"  # happy, sad, excited, confused, etc.
        self.last_messages: List[Message] = []
        self.user_preferences: Dict[str, Any] = {}
        self.conversation_start: datetime = datetime.now()
    
    def add_message(self, message: Message):
        self.last_messages.append(message)
        # Keep only last 10 messages for context
        if len(self.last_messages) > 10:
            self.last_messages = self.last_messages[-10:]

class EnhancedSocialBot:
    def __init__(self, platform: BotPlatform, bot_name: str = "AIOps Buddy"):
        self.platform = platform
        self.bot_name = bot_name
        self.conversations: Dict[str, ConversationContext] = {}
        self.users: Dict[str, User] = {}
        self.fun_facts = self._load_fun_facts()
        self.conversation_starters = self._load_conversation_starters()
        self.team_activities = self._load_team_activities()
        
        # Personality traits
        self.personality = {
            "humor_level": 0.7,  # How often to make jokes
            "emoji_usage": 0.8,  # How often to use emojis
            "casualness": 0.6,   # How casual vs professional
            "curiosity": 0.8,    # How often to ask questions
            "supportiveness": 0.9  # How supportive to be
        }
    
    def _load_fun_facts(self) -> List[str]:
        """Load fun facts for conversation"""
        return [
            "Did you know? Octopuses have three hearts! 🐙",
            "Fun fact: Honey never spoils! Archaeologists have found edible honey in ancient Egyptian tombs 🍯",
            "Cool tidbit: A group of flamingos is called a 'flamboyance' 🦩✨",
            "Tech fact: The first computer bug was an actual bug - a moth found in a Harvard computer in 1947! 🐛💻",
            "Space fact: Venus rotates so slowly that a day on Venus is longer than its year! 🪐",
            "Ocean fact: We've explored less than 5% of our oceans - there's so much mystery down there! 🌊",
            "Psychology fact: Smiling can actually make you feel happier, even if you fake it! 😊",
            "Animal fact: Dolphins have names for each other - they use unique whistle signatures! 🐬"
        ]
    
    def _load_conversation_starters(self) -> List[str]:
        """Load conversation starters for different situations"""
        return [
            "What's the most interesting thing you've learned this week? 🤔",
            "If you could have dinner with anyone (alive or historical), who would it be? 🍽️",
            "What's your go-to productivity hack? ⚡",
            "Any exciting weekend plans coming up? 🎉",
            "What's been the highlight of your day so far? ☀️",
            "If you could master any skill instantly, what would it be? 🚀",
            "What's your favorite way to unwind after work? 😌",
            "Any good book/show/movie recommendations? 📚🎬",
            "What's something you're grateful for today? 🙏",
            "If you could travel anywhere right now, where would you go? ✈️"
        ]
    
    def _load_team_activities(self) -> List[Dict[str, str]]:
        """Load team building activities and games"""
        return [
            {
                "name": "Two Truths and a Lie",
                "description": "Share two true facts and one lie about yourself - let others guess which is which!",
                "participants": "3+",
                "time": "10-15 minutes"
            },
            {
                "name": "Virtual Coffee Chat",
                "description": "Random coffee pairings for 15-minute informal chats",
                "participants": "2",
                "time": "15 minutes"
            },
            {
                "name": "Show and Tell",
                "description": "Share something interesting from your workspace or hobby",
                "participants": "Any",
                "time": "5 minutes per person"
            },
            {
                "name": "Emoji Story Challenge",
                "description": "Tell a story using only emojis, others guess what happened!",
                "participants": "3+",
                "time": "10 minutes"
            },
            {
                "name": "Quick Draw",
                "description": "30-second drawing challenge with random prompts",
                "participants": "Any",
                "time": "5-10 minutes"
            }
        ]
    
    def get_conversation_context(self, channel_id: str) -> ConversationContext:
        """Get or create conversation context for a channel"""
        if channel_id not in self.conversations:
            self.conversations[channel_id] = ConversationContext()
        return self.conversations[channel_id]
    
    def analyze_message_sentiment(self, content: str) -> str:
        """Analyze message sentiment (simplified implementation)"""
        positive_words = ["good", "great", "awesome", "amazing", "happy", "excited", "love", "fantastic"]
        negative_words = ["bad", "terrible", "awful", "sad", "angry", "frustrated", "hate", "horrible"]
        
        content_lower = content.lower()
        
        positive_count = sum(1 for word in positive_words if word in content_lower)
        negative_count = sum(1 for word in negative_words if word in content_lower)
        
        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"
    
    def detect_conversation_topic(self, content: str) -> Optional[str]:
        """Detect the main topic of conversation"""
        topics = {
            "work": ["project", "meeting", "deadline", "task", "work", "job", "office"],
            "technology": ["code", "programming", "software", "tech", "computer", "ai", "api"],
            "food": ["food", "lunch", "dinner", "recipe", "restaurant", "cooking", "eat"],
            "sports": ["game", "match", "team", "score", "sport", "football", "basketball"],
            "weather": ["weather", "rain", "sunny", "cold", "hot", "snow", "temperature"],
            "movies": ["movie", "film", "cinema", "watch", "netflix", "series", "show"],
            "music": ["music", "song", "band", "concert", "listen", "album", "artist"],
            "travel": ["travel", "trip", "vacation", "visit", "country", "city", "flight"]
        }
        
        content_lower = content.lower()
        for topic, keywords in topics.items():
            if any(keyword in content_lower for keyword in keywords):
                return topic
        
        return None
    
    async def generate_casual_response(self, message: Message) -> str:
        """Generate a casual, conversational response"""
        context = self.get_conversation_context(message.channel_id)
        context.add_message(message)
        
        sentiment = self.analyze_message_sentiment(message.content)
        topic = self.detect_conversation_topic(message.content)
        
        # Update context
        if topic:
            context.topic = topic
        context.mood = sentiment
        
        # Generate response based on context and personality
        response = await self._craft_contextual_response(message, context, sentiment, topic)
        
        return response
    
    async def _craft_contextual_response(self, message: Message, context: ConversationContext,
                                       sentiment: str, topic: Optional[str]) -> str:
        """Craft a contextual response based on the conversation"""
        content = message.content.lower()
        
        # Greeting responses
        if any(greeting in content for greeting in ["hello", "hi", "hey", "good morning", "good afternoon"]):
            greetings = [
                f"Hey there, {message.author_name}! 👋 How's your day going?",
                f"Hi {message.author_name}! 😊 Great to see you!",
                f"Hello! ✨ What's new and exciting in your world?",
                f"Hey hey! 🎉 Ready to make today awesome?"
            ]
            return random.choice(greetings)
        
        # Goodbye responses
        if any(goodbye in content for goodbye in ["bye", "goodbye", "see you", "gotta go", "leaving"]):
            goodbyes = [
                "Take care! 👋 Catch you later!",
                "See you soon! ✨ Have a great rest of your day!",
                "Bye for now! 😊 Don't be a stranger!",
                "Until next time! 🎈 Stay awesome!"
            ]
            return random.choice(goodbyes)
        
        # Positive sentiment responses
        if sentiment == "positive":
            if topic == "work":
                return "That's fantastic! 🚀 It's awesome when work goes well. What's been the best part?"
            elif topic == "food":
                return "Ooh, that sounds delicious! 😋 I'm getting hungry just thinking about it!"
            else:
                responses = [
                    "That's wonderful! 🌟 I love your positive energy!",
                    "Awesome sauce! 🎉 Your enthusiasm is contagious!",
                    "That's so cool! ✨ Tell me more about it!",
                    "Love to hear it! 😊 Keep that good vibe going!"
                ]
                return random.choice(responses)
        
        # Negative sentiment responses
        elif sentiment == "negative":
            supportive_responses = [
                "Oh no! 😔 That sounds tough. Want to talk about it?",
                "Aw, that's not great 💙 Sending good vibes your way!",
                "Sorry to hear that 😞 Is there anything that might help?",
                "That sounds frustrating 😕 Some days are just like that, aren't they?"
            ]
            return random.choice(supportive_responses)
        
        # Topic-specific responses
        if topic:
            return await self._generate_topic_response(topic, message, context)
        
        # Question responses
        if "?" in message.content:
            if "how are you" in content:
                return "I'm doing great! 😊 Thanks for asking! Living my best bot life and loving every minute of it!"
            elif "what do you think" in content:
                return "Hmm, that's a great question! 🤔 I think you've got a good point there. What's your take on it?"
            else:
                return "That's a really interesting question! 🤔 What got you thinking about that?"
        
        # Default conversational responses
        default_responses = [
            "Interesting! 🤔 Tell me more about that!",
            "Oh cool! ✨ I hadn't thought about it that way!",
            "That's pretty neat! 😊 What else is on your mind?",
            "Nice! 👍 Always enjoy our chats!",
            "Fascinating stuff! 🧠 You always have interesting things to share!"
        ]
        
        return random.choice(default_responses)
    
    async def _generate_topic_response(self, topic: str, message: Message, context: ConversationContext) -> str:
        """Generate topic-specific responses"""
        topic_responses = {
            "work": [
                "Work stuff, eh? 💼 Hope it's the fun kind of busy!",
                "Ah, the work life! ⚡ How's the productivity today?",
                "Work talk! 🚀 Any exciting projects on your plate?"
            ],
            "technology": [
                "Ooh, tech talk! 💻 I love geeking out about this stuff!",
                "Technology is so cool! 🤖 What's the latest you're excited about?",
                "Tech vibes! ⚡ Always fascinating how fast things change!"
            ],
            "food": [
                "Food talk! 🍕 Now you've got my attention (if I could eat, that is)!",
                "Yum! 😋 I may not eat, but I love hearing about good food!",
                "Food is life! 🍽️ What's your go-to comfort food?"
            ],
            "sports": [
                "Sports! ⚽ Are you following any exciting games lately?",
                "Athletic vibes! 🏃‍♂️ I admire people who stay active!",
                "Sports talk! 🏀 Who are you rooting for?"
            ],
            "weather": [
                "Weather chat! ☀️ The classic conversation starter! How's it looking out there?",
                "Ah, the weather! 🌤️ Always a safe topic, right?",
                "Weather updates! 🌦️ Hope it's treating you well!"
            ]
        }
        
        responses = topic_responses.get(topic, ["That's interesting! Tell me more! 😊"])
        return random.choice(responses)
    
    async def suggest_team_activity(self, channel_id: str) -> str:
        """Suggest a team building activity"""
        activity = random.choice(self.team_activities)
        
        suggestion = f"""🎉 **Team Activity Suggestion!** 🎉

**{activity['name']}**
{activity['description']}

👥 **Participants:** {activity['participants']}
⏰ **Time needed:** {activity['time']}

Who's in? React with 🙋‍♀️ if you want to join!"""
        
        return suggestion
    
    async def share_fun_fact(self) -> str:
        """Share a random fun fact"""
        fact = random.choice(self.fun_facts)
        return f"🧠 **Random Fun Fact Time!** 🧠\n\n{fact}"
    
    async def start_conversation(self, channel_id: str) -> str:
        """Start a conversation with a random starter"""
        starter = random.choice(self.conversation_starters)
        return f"💬 **Conversation Starter** 💬\n\n{starter}"
    
    async def daily_check_in(self, channel_id: str) -> str:
        """Send a daily check-in message"""
        check_ins = [
            "Good morning, team! ☀️ How's everyone feeling today? Ready to tackle whatever comes our way?",
            "Happy Tuesday! 🌟 What's one thing you're looking forward to today?",
            "Midweek check-in! 💪 How are we all doing? Any wins to celebrate?",
            "Thursday vibes! ⚡ Almost to the weekend - what's keeping you motivated?",
            "Friday feeling! 🎉 What's been the highlight of your week so far?"
        ]
        
        return random.choice(check_ins)
    
    async def handle_system_alert(self, alert_data: Dict, channel_id: str) -> str:
        """Handle system alerts in a friendly way"""
        severity = alert_data.get('severity', 'info')
        message = alert_data.get('message', 'System update')
        
        if severity == 'critical':
            emoji = "🚨"
            tone = "Heads up, team!"
        elif severity == 'warning':
            emoji = "⚠️"
            tone = "Just a heads up!"
        else:
            emoji = "ℹ️"
            tone = "Quick update!"
        
        friendly_message = f"""{emoji} **{tone}** {emoji}

{message}

Don't worry though - I'm keeping an eye on things! 👀 If you need any help or have questions, just give me a shout!"""
        
        return friendly_message
    
    async def process_message(self, message: Message) -> Optional[str]:
        """Main message processing function"""
        # Don't respond to bot messages
        if message.author_name == self.bot_name:
            return None
        
        # Update user info
        self.users[message.author_id] = User(
            id=message.author_id,
            name=message.author_name,
            platform=message.platform,
            last_interaction=datetime.now()
        )
        
        content = message.content.lower()
        
        # Command responses
        if content.startswith(f"@{self.bot_name.lower()}") or message.mentions_bot:
            # Remove bot mention from content
            clean_content = re.sub(f"@{self.bot_name.lower()}", "", content).strip()
            message.content = clean_content
            return await self.generate_casual_response(message)
        
        # Specific commands
        if "!funfact" in content:
            return await self.share_fun_fact()
        
        if "!activity" in content:
            return await self.suggest_team_activity(message.channel_id)
        
        if "!conversation" in content:
            return await self.start_conversation(message.channel_id)
        
        # Casual participation in ongoing conversations
        # Only respond sometimes to avoid spam
        if random.random() < 0.1:  # 10% chance to jump into conversation
            return await self.generate_casual_response(message)
        
        return None

# Platform-specific implementations
class SlackBot(EnhancedSocialBot):
    def __init__(self, token: str):
        super().__init__(BotPlatform.SLACK, "AIOps Buddy")
        self.token = token
    
    async def send_message(self, channel_id: str, message: str):
        """Send message to Slack channel"""
        # Implementation would use Slack API
        print(f"[SLACK] Sending to {channel_id}: {message}")
    
    async def format_message_for_slack(self, message: str) -> str:
        """Format message for Slack markdown"""
        # Convert markdown to Slack format
        message = message.replace("**", "*")  # Bold
        message = message.replace("###", "*")  # Headers
        return message

class DiscordBot(EnhancedSocialBot):
    def __init__(self, token: str):
        super().__init__(BotPlatform.DISCORD, "AIOps Buddy")
        self.token = token
    
    async def send_message(self, channel_id: str, message: str):
        """Send message to Discord channel"""
        # Implementation would use Discord API
        print(f"[DISCORD] Sending to {channel_id}: {message}")
    
    async def format_message_for_discord(self, message: str) -> str:
        """Format message for Discord markdown"""
        # Discord uses standard markdown
        return message

# Bot manager to handle multiple platforms
class SocialBotManager:
    def __init__(self):
        self.bots: Dict[BotPlatform, EnhancedSocialBot] = {}
        self.scheduled_tasks = []
    
    def add_bot(self, platform: BotPlatform, token: str):
        """Add a bot for a specific platform"""
        if platform == BotPlatform.SLACK:
            self.bots[platform] = SlackBot(token)
        elif platform == BotPlatform.DISCORD:
            self.bots[platform] = DiscordBot(token)
    
    async def process_message(self, platform: BotPlatform, message: Message) -> Optional[str]:
        """Process message through appropriate bot"""
        if platform in self.bots:
            return await self.bots[platform].process_message(message)
        return None
    
    async def schedule_daily_check_ins(self):
        """Schedule daily check-in messages"""
        for platform, bot in self.bots.items():
            # This would be scheduled to run at specific times
            for channel_id in ["general", "team-chat"]:  # Example channels
                check_in = await bot.daily_check_in(channel_id)
                print(f"[{platform.value.upper()}] Daily check-in: {check_in}")
    
    async def broadcast_system_alert(self, alert_data: Dict):
        """Broadcast system alert to all platforms"""
        for platform, bot in self.bots.items():
            for channel_id in ["alerts", "general"]:  # Example channels
                alert_message = await bot.handle_system_alert(alert_data, channel_id)
                print(f"[{platform.value.upper()}] Alert: {alert_message}")

# Example usage and testing
async def demo_social_bot():
    """Demonstrate the social bot functionality"""
    print("🤖 Enhanced Social Bot Demo 🤖\n")
    
    # Create bot manager
    manager = SocialBotManager()
    manager.add_bot(BotPlatform.SLACK, "slack-token")
    manager.add_bot(BotPlatform.DISCORD, "discord-token")
    
    # Simulate some messages
    test_messages = [
        Message("1", "Hey @AIOps Buddy, how are you?", "user1", "Alice", "general", 
                datetime.now(), BotPlatform.SLACK, mentions_bot=True),
        Message("2", "I'm having a great day at work!", "user2", "Bob", "general", 
                datetime.now(), BotPlatform.DISCORD),
        Message("3", "Anyone want to grab lunch?", "user3", "Charlie", "general", 
                datetime.now(), BotPlatform.SLACK),
        Message("4", "!funfact", "user1", "Alice", "general", 
                datetime.now(), BotPlatform.DISCORD),
        Message("5", "!activity", "user2", "Bob", "team-chat", 
                datetime.now(), BotPlatform.SLACK)
    ]
    
    # Process messages
    for message in test_messages:
        response = await manager.process_message(message.platform, message)
        if response:
            print(f"👤 {message.author_name}: {message.content}")
            print(f"🤖 AIOps Buddy: {response}\n")
    
    # Demo system alert
    print("📢 System Alert Demo:")
    alert = {
        "severity": "warning",
        "message": "CPU usage is above 80% on server-1"
    }
    await manager.broadcast_system_alert(alert)
    
    # Demo daily check-in
    print("\n☀️ Daily Check-in Demo:")
    await manager.schedule_daily_check_ins()

if __name__ == "__main__":
    asyncio.run(demo_social_bot())