"""
Free APIs Integration System
Integrate multiple free-tier APIs for real-time data and remove hardcoded values
"""

import asyncio
import aiohttp
import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging
from abc import ABC, abstractmethod

@dataclass
class APIConfig:
    name: str
    base_url: str
    api_key: Optional[str]
    rate_limit_per_minute: int
    free_tier_limit: int
    endpoints: Dict[str, str]

@dataclass
class APIResponse:
    success: bool
    data: Any
    error_message: Optional[str]
    response_time_ms: float
    api_name: str

class APIIntegration(ABC):
    """Base class for API integrations"""
    
    def __init__(self, config: APIConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_count = 0
        self.last_reset = datetime.now()
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def make_request(self, endpoint: str, params: Dict = None, headers: Dict = None) -> APIResponse:
        """Make API request with rate limiting and error handling"""
        start_time = datetime.now()
        
        # Check rate limiting
        if not self._check_rate_limit():
            return APIResponse(
                success=False,
                data=None,
                error_message="Rate limit exceeded",
                response_time_ms=0,
                api_name=self.config.name
            )
        
        url = f"{self.config.base_url}{endpoint}"
        
        # Add API key to headers if available
        if self.config.api_key:
            if not headers:
                headers = {}
            headers['Authorization'] = f"Bearer {self.config.api_key}"
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                
                if response.status == 200:
                    data = await response.json()
                    return APIResponse(
                        success=True,
                        data=data,
                        error_message=None,
                        response_time_ms=response_time,
                        api_name=self.config.name
                    )
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        data=None,
                        error_message=f"HTTP {response.status}: {error_text}",
                        response_time_ms=response_time,
                        api_name=self.config.name
                    )
        
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            return APIResponse(
                success=False,
                data=None,
                error_message=str(e),
                response_time_ms=response_time,
                api_name=self.config.name
            )
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        now = datetime.now()
        
        # Reset counter every minute
        if (now - self.last_reset).total_seconds() >= 60:
            self.request_count = 0
            self.last_reset = now
        
        if self.request_count >= self.config.rate_limit_per_minute:
            return False
        
        self.request_count += 1
        return True
    
    @abstractmethod
    async def get_data(self) -> Dict[str, Any]:
        """Get data from the API"""
        pass

class WeatherAPI(APIIntegration):
    """OpenWeatherMap API integration (free tier: 60 calls/minute, 1000 calls/day)"""
    
    def __init__(self, api_key: str):
        config = APIConfig(
            name="OpenWeatherMap",
            base_url="https://api.openweathermap.org/data/2.5/",
            api_key=api_key,
            rate_limit_per_minute=60,
            free_tier_limit=1000,
            endpoints={
                "current": "weather",
                "forecast": "forecast"
            }
        )
        super().__init__(config)
    
    async def get_data(self, city: str = "London") -> Dict[str, Any]:
        """Get current weather data"""
        params = {
            "q": city,
            "appid": self.config.api_key,
            "units": "metric"
        }
        
        response = await self.make_request(
            self.config.endpoints["current"],
            params=params
        )
        
        if response.success:
            weather_data = response.data
            return {
                "temperature": weather_data["main"]["temp"],
                "humidity": weather_data["main"]["humidity"],
                "pressure": weather_data["main"]["pressure"],
                "description": weather_data["weather"][0]["description"],
                "wind_speed": weather_data["wind"]["speed"],
                "city": weather_data["name"],
                "country": weather_data["sys"]["country"]
            }
        else:
            return {"error": response.error_message}

class NewsAPI(APIIntegration):
    """NewsAPI integration (free tier: 100 requests/day)"""
    
    def __init__(self, api_key: str):
        config = APIConfig(
            name="NewsAPI",
            base_url="https://newsapi.org/v2/",
            api_key=api_key,
            rate_limit_per_minute=50,
            free_tier_limit=100,
            endpoints={
                "top_headlines": "top-headlines",
                "everything": "everything"
            }
        )
        super().__init__(config)
    
    async def get_data(self, category: str = "technology") -> Dict[str, Any]:
        """Get top headlines"""
        params = {
            "category": category,
            "country": "us",
            "pageSize": 5,
            "apiKey": self.config.api_key
        }
        
        response = await self.make_request(
            self.config.endpoints["top_headlines"],
            params=params
        )
        
        if response.success:
            news_data = response.data
            articles = []
            for article in news_data.get("articles", [])[:5]:
                articles.append({
                    "title": article["title"],
                    "description": article["description"],
                    "url": article["url"],
                    "published_at": article["publishedAt"],
                    "source": article["source"]["name"]
                })
            return {"articles": articles, "total_results": news_data.get("totalResults", 0)}
        else:
            return {"error": response.error_message}

class CryptoAPI(APIIntegration):
    """CoinGecko API integration (free tier: no API key required, good rate limits)"""
    
    def __init__(self):
        config = APIConfig(
            name="CoinGecko",
            base_url="https://api.coingecko.com/api/v3/",
            api_key=None,
            rate_limit_per_minute=50,
            free_tier_limit=10000,
            endpoints={
                "prices": "simple/price",
                "trending": "search/trending"
            }
        )
        super().__init__(config)
    
    async def get_data(self) -> Dict[str, Any]:
        """Get cryptocurrency prices"""
        params = {
            "ids": "bitcoin,ethereum,litecoin,cardano,polkadot",
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        
        response = await self.make_request(
            self.config.endpoints["prices"],
            params=params
        )
        
        if response.success:
            crypto_data = response.data
            prices = {}
            for coin, data in crypto_data.items():
                prices[coin] = {
                    "price_usd": data["usd"],
                    "change_24h": data.get("usd_24h_change", 0)
                }
            return {"prices": prices}
        else:
            return {"error": response.error_message}

class QuoteAPI(APIIntegration):
    """Quotable API integration (free, no API key required)"""
    
    def __init__(self):
        config = APIConfig(
            name="Quotable",
            base_url="https://api.quotable.io/",
            api_key=None,
            rate_limit_per_minute=60,
            free_tier_limit=10000,
            endpoints={
                "random": "random",
                "quotes": "quotes"
            }
        )
        super().__init__(config)
    
    async def get_data(self) -> Dict[str, Any]:
        """Get inspirational quote"""
        params = {
            "tags": "inspirational|motivational|success",
            "maxLength": 150
        }
        
        response = await self.make_request(
            self.config.endpoints["random"],
            params=params
        )
        
        if response.success:
            quote_data = response.data
            return {
                "quote": quote_data["content"],
                "author": quote_data["author"],
                "tags": quote_data.get("tags", [])
            }
        else:
            return {"error": response.error_message}

class IPLocationAPI(APIIntegration):
    """IP Geolocation API (free tier: 1000 requests/month)"""
    
    def __init__(self, api_key: str):
        config = APIConfig(
            name="IPGeolocation",
            base_url="https://api.ipgeolocation.io/",
            api_key=api_key,
            rate_limit_per_minute=30,
            free_tier_limit=1000,
            endpoints={
                "ipgeo": "ipgeo"
            }
        )
        super().__init__(config)
    
    async def get_data(self, ip_address: str = None) -> Dict[str, Any]:
        """Get IP geolocation data"""
        params = {
            "apiKey": self.config.api_key
        }
        
        if ip_address:
            params["ip"] = ip_address
        
        response = await self.make_request(
            self.config.endpoints["ipgeo"],
            params=params
        )
        
        if response.success:
            location_data = response.data
            return {
                "ip": location_data["ip"],
                "country": location_data["country_name"],
                "city": location_data["city"],
                "region": location_data["state_prov"],
                "timezone": location_data["time_zone"]["name"],
                "isp": location_data["isp"]
            }
        else:
            return {"error": response.error_message}

class JSONPlaceholderAPI(APIIntegration):
    """JSONPlaceholder API for testing (completely free)"""
    
    def __init__(self):
        config = APIConfig(
            name="JSONPlaceholder",
            base_url="https://jsonplaceholder.typicode.com/",
            api_key=None,
            rate_limit_per_minute=100,
            free_tier_limit=10000,
            endpoints={
                "posts": "posts",
                "users": "users",
                "todos": "todos"
            }
        )
        super().__init__(config)
    
    async def get_data(self) -> Dict[str, Any]:
        """Get sample posts data"""
        response = await self.make_request(
            self.config.endpoints["posts"],
            params={"_limit": 5}
        )
        
        if response.success:
            posts = response.data
            return {
                "posts": [{
                    "id": post["id"],
                    "title": post["title"],
                    "body": post["body"][:100] + "..." if len(post["body"]) > 100 else post["body"]
                } for post in posts]
            }
        else:
            return {"error": response.error_message}

class FreeAPIAggregator:
    """Aggregates data from multiple free APIs"""
    
    def __init__(self):
        self.apis: Dict[str, APIIntegration] = {}
        self.cache: Dict[str, Dict] = {}
        self.cache_duration = timedelta(minutes=5)  # Cache for 5 minutes
        self.last_cache_update: Dict[str, datetime] = {}
    
    def add_api(self, name: str, api_instance: APIIntegration):
        """Add an API to the aggregator"""
        self.apis[name] = api_instance
    
    def _is_cache_valid(self, api_name: str) -> bool:
        """Check if cached data is still valid"""
        if api_name not in self.last_cache_update:
            return False
        
        return (datetime.now() - self.last_cache_update[api_name]) < self.cache_duration
    
    async def get_enriched_data(self) -> Dict[str, Any]:
        """Get data from all available APIs"""
        enriched_data = {
            "timestamp": datetime.now().isoformat(),
            "apis_status": {},
            "data": {}
        }
        
        # Weather data
        if "weather" in self.apis:
            if self._is_cache_valid("weather"):
                enriched_data["data"]["weather"] = self.cache["weather"]
            else:
                async with self.apis["weather"] as weather_api:
                    weather_data = await weather_api.get_data()
                    enriched_data["data"]["weather"] = weather_data
                    if "error" not in weather_data:
                        self.cache["weather"] = weather_data
                        self.last_cache_update["weather"] = datetime.now()
            
            enriched_data["apis_status"]["weather"] = "cached" if self._is_cache_valid("weather") else "fresh"
        
        # News data
        if "news" in self.apis:
            if self._is_cache_valid("news"):
                enriched_data["data"]["news"] = self.cache["news"]
            else:
                async with self.apis["news"] as news_api:
                    news_data = await news_api.get_data("technology")
                    enriched_data["data"]["news"] = news_data
                    if "error" not in news_data:
                        self.cache["news"] = news_data
                        self.last_cache_update["news"] = datetime.now()
            
            enriched_data["apis_status"]["news"] = "cached" if self._is_cache_valid("news") else "fresh"
        
        # Crypto data
        if "crypto" in self.apis:
            if self._is_cache_valid("crypto"):
                enriched_data["data"]["crypto"] = self.cache["crypto"]
            else:
                async with self.apis["crypto"] as crypto_api:
                    crypto_data = await crypto_api.get_data()
                    enriched_data["data"]["crypto"] = crypto_data
                    if "error" not in crypto_data:
                        self.cache["crypto"] = crypto_data
                        self.last_cache_update["crypto"] = datetime.now()
            
            enriched_data["apis_status"]["crypto"] = "cached" if self._is_cache_valid("crypto") else "fresh"
        
        # Quote data
        if "quotes" in self.apis:
            if self._is_cache_valid("quotes"):
                enriched_data["data"]["quote"] = self.cache["quotes"]
            else:
                async with self.apis["quotes"] as quote_api:
                    quote_data = await quote_api.get_data()
                    enriched_data["data"]["quote"] = quote_data
                    if "error" not in quote_data:
                        self.cache["quotes"] = quote_data
                        self.last_cache_update["quotes"] = datetime.now()
            
            enriched_data["apis_status"]["quotes"] = "cached" if self._is_cache_valid("quotes") else "fresh"
        
        # Test data (always available)
        if "test" in self.apis:
            async with self.apis["test"] as test_api:
                test_data = await test_api.get_data()
                enriched_data["data"]["sample_posts"] = test_data
        
        return enriched_data

# Configuration management
class APIConfigManager:
    """Manages API configurations and credentials"""
    
    def __init__(self, config_file: str = "api_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, str]:
        """Load API configuration from file or environment"""
        config = {}
        
        # Try to load from file first
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
        except Exception as e:
            logging.warning(f"Could not load config file: {e}")
        
        # Override with environment variables
        env_mappings = {
            "OPENWEATHER_API_KEY": "weather_api_key",
            "NEWS_API_KEY": "news_api_key",
            "IP_GEOLOCATION_API_KEY": "ip_geolocation_api_key"
        }
        
        for env_var, config_key in env_mappings.items():
            if env_var in os.environ:
                config[config_key] = os.environ[env_var]
        
        return config
    
    def get_api_key(self, service: str) -> Optional[str]:
        """Get API key for a service"""
        return self.config.get(f"{service}_api_key")
    
    def create_sample_config(self):
        """Create a sample configuration file"""
        sample_config = {
            "weather_api_key": "your_openweather_api_key_here",
            "news_api_key": "your_news_api_key_here",
            "ip_geolocation_api_key": "your_ip_geolocation_api_key_here"
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(sample_config, f, indent=2)
        
        print(f"Sample configuration created at {self.config_file}")
        print("Please fill in your API keys and restart the application.")

# Main integration class
class RealTimeDataProvider:
    """Main class for providing real-time data from various sources"""
    
    def __init__(self):
        self.config_manager = APIConfigManager()
        self.aggregator = FreeAPIAggregator()
        self._setup_apis()
    
    def _setup_apis(self):
        """Setup available APIs based on configuration"""
        # Always available APIs (no key required)
        self.aggregator.add_api("crypto", CryptoAPI())
        self.aggregator.add_api("quotes", QuoteAPI())
        self.aggregator.add_api("test", JSONPlaceholderAPI())
        
        # APIs that require keys
        weather_key = self.config_manager.get_api_key("weather")
        if weather_key and weather_key != "your_openweather_api_key_here":
            self.aggregator.add_api("weather", WeatherAPI(weather_key))
        
        news_key = self.config_manager.get_api_key("news")
        if news_key and news_key != "your_news_api_key_here":
            self.aggregator.add_api("news", NewsAPI(news_key))
        
        ip_key = self.config_manager.get_api_key("ip_geolocation")
        if ip_key and ip_key != "your_ip_geolocation_api_key_here":
            self.aggregator.add_api("ip_location", IPLocationAPI(ip_key))
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get enriched data for dashboard"""
        return await self.aggregator.get_enriched_data()
    
    def get_available_apis(self) -> List[str]:
        """Get list of available API integrations"""
        return list(self.aggregator.apis.keys())

# Example usage
async def demo_free_apis():
    """Demonstrate the free APIs integration"""
    print("🌐 Free APIs Integration Demo 🌐\n")
    
    # Initialize data provider
    provider = RealTimeDataProvider()
    
    print(f"Available APIs: {provider.get_available_apis()}\n")
    
    # Get enriched data
    dashboard_data = await provider.get_dashboard_data()
    
    print("📊 Dashboard Data:")
    print(f"Timestamp: {dashboard_data['timestamp']}")
    print(f"APIs Status: {dashboard_data['apis_status']}")
    
    # Display weather data
    if "weather" in dashboard_data["data"]:
        weather = dashboard_data["data"]["weather"]
        if "error" not in weather:
            print(f"\n🌤️ Weather in {weather['city']}: {weather['temperature']}°C, {weather['description']}")
        else:
            print(f"\n❌ Weather API Error: {weather['error']}")
    
    # Display crypto data
    if "crypto" in dashboard_data["data"]:
        crypto = dashboard_data["data"]["crypto"]
        if "error" not in crypto:
            print("\n💰 Crypto Prices:")
            for coin, data in crypto["prices"].items():
                change_emoji = "📈" if data["change_24h"] > 0 else "📉"
                print(f"  {coin.title()}: ${data['price_usd']:,.2f} {change_emoji} {data['change_24h']:.2f}%")
        else:
            print(f"\n❌ Crypto API Error: {crypto['error']}")
    
    # Display inspirational quote
    if "quote" in dashboard_data["data"]:
        quote = dashboard_data["data"]["quote"]
        if "error" not in quote:
            print(f"\n💭 Quote of the moment:")
            print(f"  \"{quote['quote']}\" - {quote['author']}")
        else:
            print(f"\n❌ Quote API Error: {quote['error']}")
    
    # Display news
    if "news" in dashboard_data["data"]:
        news = dashboard_data["data"]["news"]
        if "error" not in news:
            print(f"\n📰 Latest Tech News ({news.get('total_results', 0)} total):")
            for article in news.get("articles", [])[:3]:
                print(f"  • {article['title']}")
                print(f"    Source: {article['source']}")
        else:
            print(f"\n❌ News API Error: {news['error']}")

if __name__ == "__main__":
    # Create sample config if it doesn't exist
    config_manager = APIConfigManager()
    if not os.path.exists("api_config.json"):
        config_manager.create_sample_config()
    else:
        asyncio.run(demo_free_apis())