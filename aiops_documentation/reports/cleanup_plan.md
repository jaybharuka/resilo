# AIOps Enterprise Platform - Project Cleanup Plan

## Files to Keep (Production-Ready):
- realtime_api_server.py (Main API server)
- dashboard/ (React frontend)
- .env (Configuration)
- requirements.txt (Dependencies)
- start_aiops_system.bat (Startup script)

## Files to Remove (Test/Demo files):
- test_*.py (All test files)
- demo_*.py (All demo files)
- simple_*.py (Simple/prototype versions)
- enhanced_*.py (Older enhanced versions)
- *_demo.py (Demo files)
- *.html (Static HTML files - replaced by React)
- hackathon_demo.py
- quick_*.py
- check_*.py
- debug_*.py

## Files to Archive (Reference):
- documentation/ (Keep for reference)
- config/ (Configuration templates)
- COMPREHENSIVE_DOCUMENTATION.md
- architecture_plan.md

## New Structure to Create:
```
aiops-platform/
├── backend/
│   ├── api/
│   ├── services/
│   ├── models/
│   └── utils/
├── frontend/
│   └── dashboard/
├── docs/
├── config/
├── scripts/
└── tests/
```