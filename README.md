# 🤖 AIOps Bot - Intelligent Operations Dashboard

[![Deploy](https://github.com/jaybh/Ai-Ops-Bot/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/jaybh/Ai-Ops-Bot/actions/workflows/deploy.yml)

A comprehensive AI-powered operations monitoring platform combining free Hugging Face AI models with a modern React dashboard for enterprise-grade system monitoring and insights.

## 🌟 Features

### 🤖 AI-Powered Monitoring
- **Dual AI Engine**: Gemini Pro + Free Hugging Face models
- **Sentiment Analysis**: Monitor user feedback and system logs
- **Issue Classification**: Automatic categorization of problems
- **Log Summarization**: AI-powered log analysis and insights
- **Intelligent Chat**: Real-time AI assistant for troubleshooting

### 📊 Real-Time Dashboard
- **System Metrics**: CPU, Memory, Disk, Network monitoring
- **Performance Charts**: Interactive time-series visualizations
- **AI Insights Panel**: Smart recommendations and alerts
- **Alert Management**: Centralized notification system
- **Status Indicators**: Real-time service health monitoring

### 🎨 Modern UI/UX
- **Material-UI Design**: Professional, responsive interface
- **Dark/Light Themes**: Customizable appearance
- **Smooth Animations**: Framer Motion-powered interactions
- **Mobile Responsive**: Works on all device sizes
- **Real-time Updates**: Live data streaming

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 16+
- 4GB RAM minimum
- Internet connection (for AI models)

### 🔥 One-Click Launch
```bash
# Windows
start_dashboard.bat

# Manual start (all platforms)
python api_server.py &
cd dashboard && npm start
```

### 📦 Manual Installation

#### Backend Setup
```bash
# Install Python dependencies
pip install flask flask-cors psutil transformers torch

# Start API server
python api_server.py
```

#### Frontend Setup
```bash
# Navigate to dashboard
cd dashboard

# Install dependencies
npm install

# Start development server
npm start
```

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health check |
| `/api/system` | GET | Current system metrics |
| `/api/insights` | GET | AI-generated insights |
| `/api/alerts` | GET | Recent alerts and notifications |
| `/api/chat` | POST | Chat with AI assistant |
| `/api/analyze` | POST | AI text analysis |
| `/api/performance` | GET | Historical performance data |

## 🧠 AI Capabilities

### Hugging Face Models Used
- **Sentiment Analysis**: `distilbert-base-uncased-finetuned-sst-2-english`
- **Issue Classification**: `distilbert-base-uncased`
- **Text Summarization**: `distilbart-cnn-12-6`
- **Q&A System**: `distilbert-base-cased-distilled-squad`
- **Emotion Detection**: `j-hartmann/emotion-english-distilroberta-base`

### Sample AI Interactions
```python
# Sentiment Analysis
analyze_sentiment("The system is running perfectly!")
# → {'sentiment': 'POSITIVE', 'confidence': 0.9998}

# Issue Classification
classify_issue("Database connection timeout")
# → {'category': 'database', 'confidence': 0.95}

# Log Summarization
summarize_logs("Multiple error logs...")
# → "Critical database connectivity issues detected"
```

## 📊 Dashboard Components

### System Metrics
- Real-time CPU, Memory, Disk usage
- Network throughput monitoring
- System temperature tracking
- Process count and uptime

### Performance Charts
- Historical performance trends
- Network traffic visualization
- Temperature monitoring
- Interactive tooltips and legends

### AI Insights Panel
- Smart performance recommendations
- Anomaly detection alerts
- Optimization suggestions
- Confidence-scored insights

### Real-time Chat
- AI-powered troubleshooting assistant
- Natural language query support
- Context-aware responses
- Integration with system metrics

## 🔧 Configuration

### Environment Variables
```bash
# API Configuration
API_PORT=5000
API_HOST=0.0.0.0

# AI Model Settings
HF_MODEL_CACHE_DIR=./models
GEMINI_API_KEY=your_key_here

# Dashboard Settings
REACT_APP_API_URL=http://localhost:5000
```

### Customization
- Modify `api_server.py` for backend logic
- Update React components in `dashboard/src/components/`
- Customize themes in `dashboard/src/App.js`
- Add new AI models in `huggingface_ai_integration.py`

## 🏗️ Architecture

```
AIOps Bot System
├── Backend (Python Flask)
│   ├── api_server.py          # Main API server
│   ├── enhanced_aiops_chatbot.py  # Core bot logic
│   └── huggingface_ai_integration.py  # AI models
├── Frontend (React)
│   ├── src/
│   │   ├── components/        # UI components
│   │   ├── services/          # API integration
│   │   └── App.js            # Main application
│   └── package.json          # Dependencies
└── CI/CD Pipeline
    ├── .github/workflows/     # GitHub Actions
    └── deployment/           # Deployment scripts
```

## 🎯 Use Cases

### DevOps Teams
- Monitor production systems
- Automated incident response
- Performance optimization
- Capacity planning

### IT Operations
- Infrastructure monitoring
- Predictive maintenance
- Alert management
- System health dashboards

### Business Intelligence
- Performance reporting
- Cost optimization insights
- SLA monitoring
- Trend analysis

## 🔐 Security Features

- CORS protection
- Input validation
- API rate limiting
- Secure communication
- Error handling

## 📈 Performance

### System Requirements
- **Minimum**: 2GB RAM, 1 CPU core
- **Recommended**: 4GB RAM, 2 CPU cores
- **Storage**: 1GB for models and cache
- **Network**: Broadband for model downloads

### Optimization Tips
- Use local model caching
- Enable compression
- Implement connection pooling
- Monitor memory usage

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Hugging Face**: For providing free AI models
- **Material-UI**: For beautiful React components
- **Framer Motion**: For smooth animations
- **Flask**: For lightweight backend framework
- **React**: For powerful frontend framework

## 📞 Support

- 📧 Email: support@aiopsbot.com
- 💬 Discord: AIOps Community
- 📖 Documentation: [Wiki](https://github.com/aiopsbot/wiki)
- 🐛 Issues: [GitHub Issues](https://github.com/aiopsbot/issues)

---

<div align="center">

**🎉 Built with ❤️ for the DevOps Community**

*Making AI-powered operations accessible to everyone*

[![Demo](https://img.shields.io/badge/🎮-Live%20Demo-blue)](http://localhost:3000)
[![API](https://img.shields.io/badge/🔌-API%20Docs-green)](http://localhost:5000/api/health)
[![AI](https://img.shields.io/badge/🤖-AI%20Powered-purple)](https://huggingface.co/)

</div>