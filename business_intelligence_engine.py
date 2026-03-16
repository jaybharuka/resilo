#!/usr/bin/env python3
"""
AIOps Bot - Business Intelligence Engine
Advanced executive dashboards, ROI analytics, and strategic insights generation
"""

import asyncio
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict
import math

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MetricCategory(Enum):
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    SECURITY = "security"
    PERFORMANCE = "performance"
    COMPLIANCE = "compliance"

class TrendDirection(Enum):
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    VOLATILE = "volatile"

@dataclass
class KPIMetric:
    """Key Performance Indicator definition"""
    name: str
    category: MetricCategory
    current_value: float
    target_value: float
    previous_value: float
    unit: str
    trend: TrendDirection
    confidence: float
    last_updated: datetime
    description: str

@dataclass
class ROIAnalysis:
    """Return on Investment analysis"""
    initiative: str
    investment_amount: float
    savings_achieved: float
    roi_percentage: float
    payback_period_months: float
    net_present_value: float
    confidence_score: float
    risk_factors: List[str]

@dataclass
class StrategicInsight:
    """Strategic business insight"""
    title: str
    category: str
    priority: str  # high, medium, low
    impact_score: float
    description: str
    recommendations: List[str]
    data_sources: List[str]
    confidence: float
    generated_at: datetime

@dataclass
class ExecutiveSummary:
    """Executive summary for leadership"""
    period: str
    overall_health_score: float
    key_achievements: List[str]
    critical_issues: List[str]
    financial_impact: Dict[str, float]
    strategic_recommendations: List[str]
    kpi_summary: Dict[str, Any]

class BusinessIntelligenceEngine:
    """Advanced Business Intelligence Engine for AIOps"""
    
    def __init__(self, db_path: str = "aiops_bi.db"):
        """Initialize Business Intelligence Engine"""
        self.db_path = db_path
        self.kpis: Dict[str, KPIMetric] = {}
        self.roi_analyses: List[ROIAnalysis] = []
        self.strategic_insights: List[StrategicInsight] = []
        self.executive_summaries: List[ExecutiveSummary] = []
        
        # Initialize database
        self._init_database()
        
        # Define standard KPIs
        self._initialize_standard_kpis()
        
        logger.info("Business Intelligence Engine initialized")
    
    def _init_database(self):
        """Initialize SQLite database for BI data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # KPI metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS kpi_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    current_value REAL NOT NULL,
                    target_value REAL NOT NULL,
                    previous_value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    trend TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    last_updated TEXT NOT NULL,
                    description TEXT
                )
            ''')
            
            # ROI analyses table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roi_analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    initiative TEXT NOT NULL,
                    investment_amount REAL NOT NULL,
                    savings_achieved REAL NOT NULL,
                    roi_percentage REAL NOT NULL,
                    payback_period_months REAL NOT NULL,
                    net_present_value REAL NOT NULL,
                    confidence_score REAL NOT NULL,
                    risk_factors TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Strategic insights table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategic_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    impact_score REAL NOT NULL,
                    description TEXT NOT NULL,
                    recommendations TEXT,
                    data_sources TEXT,
                    confidence REAL NOT NULL,
                    generated_at TEXT NOT NULL
                )
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
    
    def _initialize_standard_kpis(self):
        """Initialize standard AIOps KPIs"""
        standard_kpis = [
            {
                "name": "Mean Time To Resolution (MTTR)",
                "category": MetricCategory.OPERATIONAL,
                "current_value": 3.2,
                "target_value": 5.0,
                "previous_value": 8.7,
                "unit": "minutes",
                "trend": TrendDirection.IMPROVING,
                "confidence": 0.94,
                "description": "Average time to resolve incidents"
            },
            {
                "name": "System Availability",
                "category": MetricCategory.OPERATIONAL,
                "current_value": 99.95,
                "target_value": 99.9,
                "previous_value": 99.87,
                "unit": "percentage",
                "trend": TrendDirection.IMPROVING,
                "confidence": 0.98,
                "description": "Overall system uptime percentage"
            },
            {
                "name": "Cost Per Incident",
                "category": MetricCategory.FINANCIAL,
                "current_value": 2847.0,
                "target_value": 5000.0,
                "previous_value": 7231.0,
                "unit": "USD",
                "trend": TrendDirection.IMPROVING,
                "confidence": 0.87,
                "description": "Average cost of handling incidents"
            },
            {
                "name": "Automation Success Rate",
                "category": MetricCategory.PERFORMANCE,
                "current_value": 89.2,
                "target_value": 85.0,
                "previous_value": 67.4,
                "unit": "percentage",
                "trend": TrendDirection.IMPROVING,
                "confidence": 0.91,
                "description": "Percentage of successful automated remediation"
            },
            {
                "name": "Security Posture Score",
                "category": MetricCategory.SECURITY,
                "current_value": 81.0,
                "target_value": 85.0,
                "previous_value": 73.5,
                "unit": "score",
                "trend": TrendDirection.IMPROVING,
                "confidence": 0.88,
                "description": "Overall security health assessment"
            },
            {
                "name": "Compliance Score",
                "category": MetricCategory.COMPLIANCE,
                "current_value": 88.5,
                "target_value": 90.0,
                "previous_value": 82.1,
                "unit": "percentage",
                "trend": TrendDirection.IMPROVING,
                "confidence": 0.93,
                "description": "Overall regulatory compliance status"
            }
        ]
        
        for kpi_data in standard_kpis:
            kpi = KPIMetric(
                name=kpi_data["name"],
                category=kpi_data["category"],
                current_value=kpi_data["current_value"],
                target_value=kpi_data["target_value"],
                previous_value=kpi_data["previous_value"],
                unit=kpi_data["unit"],
                trend=kpi_data["trend"],
                confidence=kpi_data["confidence"],
                last_updated=datetime.now(),
                description=kpi_data["description"]
            )
            self.kpis[kpi.name] = kpi
    
    async def update_kpi(self, name: str, new_value: float) -> bool:
        """Update a KPI metric with new value"""
        try:
            if name in self.kpis:
                kpi = self.kpis[name]
                kpi.previous_value = kpi.current_value
                kpi.current_value = new_value
                kpi.last_updated = datetime.now()
                
                # Update trend analysis
                kpi.trend = self._calculate_trend(kpi.current_value, kpi.previous_value, kpi.target_value)
                
                # Save to database
                await self._save_kpi_to_db(kpi)
                
                logger.info(f"Updated KPI '{name}': {new_value} {kpi.unit}")
                return True
            else:
                logger.warning(f"KPI '{name}' not found")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update KPI '{name}': {e}")
            return False
    
    def _calculate_trend(self, current: float, previous: float, target: float) -> TrendDirection:
        """Calculate trend direction based on values"""
        try:
            change_rate = abs((current - previous) / previous) if previous != 0 else 0
            
            # High volatility threshold
            if change_rate > 0.1:
                return TrendDirection.VOLATILE
            
            # Determine if improvement is good (depends on metric type)
            improvement = current > previous
            
            # For metrics where higher is better (availability, success rate)
            # For metrics where lower is better (MTTR, cost), flip the logic
            metric_name = ""
            if "time" in str(current).lower() or "cost" in str(current).lower():
                improvement = current < previous
            
            if abs(current - previous) < 0.01:
                return TrendDirection.STABLE
            elif improvement:
                return TrendDirection.IMPROVING
            else:
                return TrendDirection.DECLINING
                
        except Exception:
            return TrendDirection.STABLE
    
    async def _save_kpi_to_db(self, kpi: KPIMetric):
        """Save KPI to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO kpi_metrics 
                (name, category, current_value, target_value, previous_value, 
                 unit, trend, confidence, last_updated, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                kpi.name, kpi.category.value, kpi.current_value, kpi.target_value,
                kpi.previous_value, kpi.unit, kpi.trend.value, kpi.confidence,
                kpi.last_updated.isoformat(), kpi.description
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to save KPI to database: {e}")
    
    async def perform_roi_analysis(self, initiative: str, investment: float, 
                                 monthly_savings: float, duration_months: int = 12) -> ROIAnalysis:
        """Perform comprehensive ROI analysis"""
        try:
            # Calculate savings achieved over period
            savings_achieved = monthly_savings * duration_months
            
            # Calculate ROI percentage
            roi_percentage = ((savings_achieved - investment) / investment) * 100 if investment > 0 else 0
            
            # Calculate payback period
            payback_period = investment / monthly_savings if monthly_savings > 0 else float('inf')
            
            # Calculate NPV (assuming 5% discount rate)
            discount_rate = 0.05
            npv = -investment
            for month in range(1, duration_months + 1):
                npv += monthly_savings / ((1 + discount_rate/12) ** month)
            
            # Assess confidence based on data quality and assumptions
            confidence_score = self._calculate_roi_confidence(initiative, investment, monthly_savings)
            
            # Identify risk factors
            risk_factors = self._identify_risk_factors(initiative, roi_percentage, payback_period)
            
            roi_analysis = ROIAnalysis(
                initiative=initiative,
                investment_amount=investment,
                savings_achieved=savings_achieved,
                roi_percentage=roi_percentage,
                payback_period_months=payback_period,
                net_present_value=npv,
                confidence_score=confidence_score,
                risk_factors=risk_factors
            )
            
            self.roi_analyses.append(roi_analysis)
            await self._save_roi_to_db(roi_analysis)
            
            logger.info(f"ROI analysis completed for '{initiative}': {roi_percentage:.1f}% ROI")
            return roi_analysis
            
        except Exception as e:
            logger.error(f"ROI analysis failed for '{initiative}': {e}")
            raise
    
    def _calculate_roi_confidence(self, initiative: str, investment: float, savings: float) -> float:
        """Calculate confidence score for ROI analysis"""
        confidence = 0.8  # Base confidence
        
        # Adjust based on initiative type
        if "automation" in initiative.lower():
            confidence += 0.1  # Automation ROI is more predictable
        if "ai" in initiative.lower() or "ml" in initiative.lower():
            confidence -= 0.1  # AI/ML ROI has more uncertainty
        
        # Adjust based on investment size
        if investment > 100000:
            confidence -= 0.05  # Larger investments have more uncertainty
        
        # Adjust based on savings predictability
        if savings < investment * 0.1:
            confidence -= 0.1  # Low savings relative to investment
        
        return max(0.5, min(0.95, confidence))
    
    def _identify_risk_factors(self, initiative: str, roi: float, payback: float) -> List[str]:
        """Identify risk factors for ROI analysis"""
        risks = []
        
        if roi < 20:
            risks.append("Low ROI may not justify investment")
        if payback > 24:
            risks.append("Long payback period increases uncertainty")
        if "new technology" in initiative.lower():
            risks.append("Technology adoption risks")
        if "staff training" in initiative.lower():
            risks.append("Training effectiveness uncertainty")
        if roi > 200:
            risks.append("Overly optimistic projections")
        
        return risks
    
    async def _save_roi_to_db(self, roi: ROIAnalysis):
        """Save ROI analysis to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO roi_analyses 
                (initiative, investment_amount, savings_achieved, roi_percentage,
                 payback_period_months, net_present_value, confidence_score,
                 risk_factors, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                roi.initiative, roi.investment_amount, roi.savings_achieved,
                roi.roi_percentage, roi.payback_period_months, roi.net_present_value,
                roi.confidence_score, json.dumps(roi.risk_factors), datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to save ROI analysis to database: {e}")
    
    async def generate_strategic_insights(self) -> List[StrategicInsight]:
        """Generate strategic insights from current data"""
        insights = []
        
        try:
            # Analyze KPI trends
            kpi_insights = self._analyze_kpi_trends()
            insights.extend(kpi_insights)
            
            # Analyze ROI patterns
            roi_insights = self._analyze_roi_patterns()
            insights.extend(roi_insights)
            
            # Generate operational insights
            operational_insights = self._generate_operational_insights()
            insights.extend(operational_insights)
            
            # Generate security insights
            security_insights = self._generate_security_insights()
            insights.extend(security_insights)
            
            # Save insights
            for insight in insights:
                await self._save_insight_to_db(insight)
            
            self.strategic_insights.extend(insights)
            logger.info(f"Generated {len(insights)} strategic insights")
            
            return insights
            
        except Exception as e:
            logger.error(f"Failed to generate strategic insights: {e}")
            return []
    
    def _analyze_kpi_trends(self) -> List[StrategicInsight]:
        """Analyze KPI trends for insights"""
        insights = []
        
        improving_metrics = [kpi for kpi in self.kpis.values() if kpi.trend == TrendDirection.IMPROVING]
        declining_metrics = [kpi for kpi in self.kpis.values() if kpi.trend == TrendDirection.DECLINING]
        
        if len(improving_metrics) >= 3:
            insights.append(StrategicInsight(
                title="Strong Operational Improvement Trend",
                category="operational",
                priority="medium",
                impact_score=7.5,
                description=f"Multiple KPIs showing improvement: {', '.join([kpi.name for kpi in improving_metrics[:3]])}",
                recommendations=[
                    "Continue current operational strategies",
                    "Document successful practices for replication",
                    "Consider expanding successful initiatives"
                ],
                data_sources=["KPI Trends"],
                confidence=0.85,
                generated_at=datetime.now()
            ))
        
        if len(declining_metrics) >= 2:
            insights.append(StrategicInsight(
                title="Performance Decline Alert",
                category="risk",
                priority="high",
                impact_score=8.0,
                description=f"Declining performance in: {', '.join([kpi.name for kpi in declining_metrics[:2]])}",
                recommendations=[
                    "Investigate root causes of performance decline",
                    "Implement corrective action plans",
                    "Increase monitoring frequency for affected areas"
                ],
                data_sources=["KPI Trends"],
                confidence=0.90,
                generated_at=datetime.now()
            ))
        
        return insights
    
    def _analyze_roi_patterns(self) -> List[StrategicInsight]:
        """Analyze ROI patterns for insights"""
        insights = []
        
        if not self.roi_analyses:
            return insights
        
        avg_roi = np.mean([roi.roi_percentage for roi in self.roi_analyses])
        high_roi_initiatives = [roi for roi in self.roi_analyses if roi.roi_percentage > 50]
        
        if avg_roi > 30:
            insights.append(StrategicInsight(
                title="Strong Investment Returns",
                category="financial",
                priority="medium",
                impact_score=7.0,
                description=f"Average ROI of {avg_roi:.1f}% indicates successful investment strategy",
                recommendations=[
                    "Scale successful investment patterns",
                    "Increase investment in high-performing areas",
                    "Share best practices across organization"
                ],
                data_sources=["ROI Analysis"],
                confidence=0.80,
                generated_at=datetime.now()
            ))
        
        if len(high_roi_initiatives) >= 2:
            insights.append(StrategicInsight(
                title="High-Value Initiative Opportunity",
                category="strategic",
                priority="high",
                impact_score=8.5,
                description=f"Multiple high-ROI initiatives identified: {', '.join([roi.initiative for roi in high_roi_initiatives[:2]])}",
                recommendations=[
                    "Prioritize funding for high-ROI initiatives",
                    "Develop similar initiatives in other areas",
                    "Create templates based on successful patterns"
                ],
                data_sources=["ROI Analysis"],
                confidence=0.85,
                generated_at=datetime.now()
            ))
        
        return insights
    
    def _generate_operational_insights(self) -> List[StrategicInsight]:
        """Generate operational insights"""
        insights = []
        
        # Check MTTR performance
        mttr_kpi = self.kpis.get("Mean Time To Resolution (MTTR)")
        if mttr_kpi and mttr_kpi.current_value < mttr_kpi.target_value:
            insights.append(StrategicInsight(
                title="Exceptional Incident Response Performance",
                category="operational",
                priority="medium",
                impact_score=7.0,
                description=f"MTTR of {mttr_kpi.current_value} minutes exceeds target of {mttr_kpi.target_value} minutes",
                recommendations=[
                    "Document current incident response procedures",
                    "Train additional teams on best practices",
                    "Consider lowering MTTR targets further"
                ],
                data_sources=["MTTR KPI"],
                confidence=0.88,
                generated_at=datetime.now()
            ))
        
        # Check automation success rate
        automation_kpi = self.kpis.get("Automation Success Rate")
        if automation_kpi and automation_kpi.current_value > 85:
            insights.append(StrategicInsight(
                title="Automation Maturity Achievement",
                category="operational",
                priority="medium",
                impact_score=7.5,
                description=f"Automation success rate of {automation_kpi.current_value}% indicates mature automation capabilities",
                recommendations=[
                    "Expand automation to additional use cases",
                    "Develop advanced AI-driven automation",
                    "Create automation center of excellence"
                ],
                data_sources=["Automation KPI"],
                confidence=0.85,
                generated_at=datetime.now()
            ))
        
        return insights
    
    def _generate_security_insights(self) -> List[StrategicInsight]:
        """Generate security insights"""
        insights = []
        
        security_kpi = self.kpis.get("Security Posture Score")
        compliance_kpi = self.kpis.get("Compliance Score")
        
        if security_kpi and security_kpi.current_value < 80:
            insights.append(StrategicInsight(
                title="Security Posture Improvement Needed",
                category="security",
                priority="high",
                impact_score=9.0,
                description=f"Security posture score of {security_kpi.current_value} below recommended threshold of 80",
                recommendations=[
                    "Conduct comprehensive security assessment",
                    "Implement additional security controls",
                    "Increase security training and awareness",
                    "Consider third-party security audit"
                ],
                data_sources=["Security KPI"],
                confidence=0.90,
                generated_at=datetime.now()
            ))
        
        if compliance_kpi and compliance_kpi.current_value >= 90:
            insights.append(StrategicInsight(
                title="Excellent Compliance Posture",
                category="compliance",
                priority="low",
                impact_score=6.0,
                description=f"Compliance score of {compliance_kpi.current_value}% demonstrates strong regulatory adherence",
                recommendations=[
                    "Maintain current compliance processes",
                    "Consider pursuing additional certifications",
                    "Share compliance best practices with industry peers"
                ],
                data_sources=["Compliance KPI"],
                confidence=0.85,
                generated_at=datetime.now()
            ))
        
        return insights
    
    async def _save_insight_to_db(self, insight: StrategicInsight):
        """Save strategic insight to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO strategic_insights 
                (title, category, priority, impact_score, description,
                 recommendations, data_sources, confidence, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                insight.title, insight.category, insight.priority, insight.impact_score,
                insight.description, json.dumps(insight.recommendations),
                json.dumps(insight.data_sources), insight.confidence,
                insight.generated_at.isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to save strategic insight to database: {e}")
    
    async def generate_executive_summary(self, period: str = "monthly") -> ExecutiveSummary:
        """Generate comprehensive executive summary"""
        try:
            # Calculate overall health score
            health_score = self._calculate_overall_health_score()
            
            # Identify key achievements
            achievements = self._identify_key_achievements()
            
            # Identify critical issues
            critical_issues = self._identify_critical_issues()
            
            # Calculate financial impact
            financial_impact = self._calculate_financial_impact()
            
            # Generate strategic recommendations
            recommendations = self._generate_strategic_recommendations()
            
            # Summarize KPIs
            kpi_summary = self._summarize_kpis()
            
            summary = ExecutiveSummary(
                period=period,
                overall_health_score=health_score,
                key_achievements=achievements,
                critical_issues=critical_issues,
                financial_impact=financial_impact,
                strategic_recommendations=recommendations,
                kpi_summary=kpi_summary
            )
            
            self.executive_summaries.append(summary)
            logger.info(f"Generated executive summary for {period} period")
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate executive summary: {e}")
            raise
    
    def _calculate_overall_health_score(self) -> float:
        """Calculate overall system health score"""
        if not self.kpis:
            return 0.0
        
        scores = []
        weights = {
            MetricCategory.OPERATIONAL: 0.3,
            MetricCategory.SECURITY: 0.25,
            MetricCategory.FINANCIAL: 0.2,
            MetricCategory.PERFORMANCE: 0.15,
            MetricCategory.COMPLIANCE: 0.1
        }
        
        for kpi in self.kpis.values():
            # Calculate percentage of target achieved
            if kpi.target_value != 0:
                achievement = min(1.0, kpi.current_value / kpi.target_value)
            else:
                achievement = 1.0 if kpi.current_value > 0 else 0.0
            
            # Weight by category
            weight = weights.get(kpi.category, 0.1)
            weighted_score = achievement * weight * 100
            scores.append(weighted_score)
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _identify_key_achievements(self) -> List[str]:
        """Identify key achievements from recent performance"""
        achievements = []
        
        # Check for KPIs exceeding targets
        for kpi in self.kpis.values():
            if kpi.current_value > kpi.target_value and kpi.trend == TrendDirection.IMPROVING:
                achievements.append(f"{kpi.name} exceeded target by {((kpi.current_value/kpi.target_value-1)*100):.1f}%")
        
        # Check for high ROI initiatives
        high_roi = [roi for roi in self.roi_analyses if roi.roi_percentage > 50]
        if high_roi:
            achievements.append(f"Achieved {len(high_roi)} high-ROI initiatives with average {np.mean([r.roi_percentage for r in high_roi]):.1f}% return")
        
        # Check for operational improvements
        mttr_kpi = self.kpis.get("Mean Time To Resolution (MTTR)")
        if mttr_kpi and mttr_kpi.trend == TrendDirection.IMPROVING:
            improvement = ((mttr_kpi.previous_value - mttr_kpi.current_value) / mttr_kpi.previous_value) * 100
            achievements.append(f"Improved incident resolution time by {improvement:.1f}%")
        
        return achievements[:5]  # Top 5 achievements
    
    def _identify_critical_issues(self) -> List[str]:
        """Identify critical issues requiring attention"""
        issues = []
        
        # Check for KPIs below target
        for kpi in self.kpis.values():
            if kpi.current_value < kpi.target_value * 0.9:  # More than 10% below target
                gap = ((kpi.target_value - kpi.current_value) / kpi.target_value) * 100
                issues.append(f"{kpi.name} is {gap:.1f}% below target")
        
        # Check for declining trends
        declining = [kpi for kpi in self.kpis.values() if kpi.trend == TrendDirection.DECLINING]
        if declining:
            issues.append(f"{len(declining)} KPIs showing declining performance")
        
        # Check for low ROI initiatives
        low_roi = [roi for roi in self.roi_analyses if roi.roi_percentage < 10]
        if low_roi:
            issues.append(f"{len(low_roi)} initiatives showing low ROI")
        
        return issues[:5]  # Top 5 critical issues
    
    def _calculate_financial_impact(self) -> Dict[str, float]:
        """Calculate financial impact metrics"""
        impact = {
            "total_investment": sum([roi.investment_amount for roi in self.roi_analyses]),
            "total_savings": sum([roi.savings_achieved for roi in self.roi_analyses]),
            "net_benefit": 0,
            "average_roi": 0
        }
        
        if self.roi_analyses:
            impact["net_benefit"] = impact["total_savings"] - impact["total_investment"]
            impact["average_roi"] = np.mean([roi.roi_percentage for roi in self.roi_analyses])
        
        return impact
    
    def _generate_strategic_recommendations(self) -> List[str]:
        """Generate strategic recommendations based on analysis"""
        recommendations = []
        
        # Based on KPI performance
        underperforming = [kpi for kpi in self.kpis.values() if kpi.current_value < kpi.target_value]
        if len(underperforming) > 2:
            recommendations.append("Focus on improving underperforming KPIs through targeted initiatives")
        
        # Based on financial performance
        if self.roi_analyses:
            avg_roi = np.mean([roi.roi_percentage for roi in self.roi_analyses])
            if avg_roi > 30:
                recommendations.append("Scale successful investment patterns to maximize returns")
            elif avg_roi < 15:
                recommendations.append("Review investment criteria and focus on higher-impact initiatives")
        
        # Based on security posture
        security_kpi = self.kpis.get("Security Posture Score")
        if security_kpi and security_kpi.current_value < 85:
            recommendations.append("Prioritize security improvements to enhance overall posture")
        
        # Based on automation success
        automation_kpi = self.kpis.get("Automation Success Rate")
        if automation_kpi and automation_kpi.current_value > 85:
            recommendations.append("Expand automation capabilities to additional operational areas")
        
        return recommendations[:5]  # Top 5 recommendations
    
    def _summarize_kpis(self) -> Dict[str, Any]:
        """Summarize KPI performance"""
        if not self.kpis:
            return {}
        
        summary = {
            "total_kpis": len(self.kpis),
            "on_target": len([kpi for kpi in self.kpis.values() if kpi.current_value >= kpi.target_value]),
            "improving": len([kpi for kpi in self.kpis.values() if kpi.trend == TrendDirection.IMPROVING]),
            "declining": len([kpi for kpi in self.kpis.values() if kpi.trend == TrendDirection.DECLINING]),
            "stable": len([kpi for kpi in self.kpis.values() if kpi.trend == TrendDirection.STABLE]),
            "average_confidence": np.mean([kpi.confidence for kpi in self.kpis.values()])
        }
        
        # Category breakdown
        summary["by_category"] = {}
        for category in MetricCategory:
            category_kpis = [kpi for kpi in self.kpis.values() if kpi.category == category]
            if category_kpis:
                summary["by_category"][category.value] = {
                    "count": len(category_kpis),
                    "on_target": len([kpi for kpi in category_kpis if kpi.current_value >= kpi.target_value]),
                    "average_performance": np.mean([kpi.current_value/kpi.target_value for kpi in category_kpis if kpi.target_value > 0])
                }
        
        return summary
    
    async def get_executive_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive data for executive dashboard"""
        try:
            # Generate latest insights if needed
            if not self.strategic_insights:
                await self.generate_strategic_insights()
            
            # Generate executive summary
            summary = await self.generate_executive_summary()
            
            dashboard_data = {
                "summary": asdict(summary),
                "kpis": {name: asdict(kpi) for name, kpi in self.kpis.items()},
                "roi_analyses": [asdict(roi) for roi in self.roi_analyses[-5:]],  # Latest 5
                "strategic_insights": [asdict(insight) for insight in self.strategic_insights[-10:]],  # Latest 10
                "performance_trends": self._get_performance_trends(),
                "financial_overview": self._get_financial_overview(),
                "security_status": self._get_security_status(),
                "operational_metrics": self._get_operational_metrics(),
                "generated_at": datetime.now().isoformat()
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Failed to get executive dashboard data: {e}")
            return {}
    
    def _get_performance_trends(self) -> Dict[str, Any]:
        """Get performance trend data"""
        trends = {}
        
        for name, kpi in self.kpis.items():
            trends[name] = {
                "current": kpi.current_value,
                "previous": kpi.previous_value,
                "target": kpi.target_value,
                "trend": kpi.trend.value,
                "performance_ratio": kpi.current_value / kpi.target_value if kpi.target_value > 0 else 1.0
            }
        
        return trends
    
    def _get_financial_overview(self) -> Dict[str, Any]:
        """Get financial overview data"""
        if not self.roi_analyses:
            return {"total_investment": 0, "total_savings": 0, "roi_summary": "No data available"}
        
        total_investment = sum([roi.investment_amount for roi in self.roi_analyses])
        total_savings = sum([roi.savings_achieved for roi in self.roi_analyses])
        average_roi = np.mean([roi.roi_percentage for roi in self.roi_analyses])
        
        return {
            "total_investment": total_investment,
            "total_savings": total_savings,
            "net_benefit": total_savings - total_investment,
            "average_roi": average_roi,
            "initiative_count": len(self.roi_analyses),
            "roi_summary": f"Average {average_roi:.1f}% ROI across {len(self.roi_analyses)} initiatives"
        }
    
    def _get_security_status(self) -> Dict[str, Any]:
        """Get security status overview"""
        security_kpi = self.kpis.get("Security Posture Score")
        compliance_kpi = self.kpis.get("Compliance Score")
        
        return {
            "security_score": security_kpi.current_value if security_kpi else 0,
            "compliance_score": compliance_kpi.current_value if compliance_kpi else 0,
            "security_trend": security_kpi.trend.value if security_kpi else "unknown",
            "compliance_trend": compliance_kpi.trend.value if compliance_kpi else "unknown",
            "overall_status": "Good" if (security_kpi and security_kpi.current_value > 80) else "Needs Attention"
        }
    
    def _get_operational_metrics(self) -> Dict[str, Any]:
        """Get operational metrics overview"""
        mttr_kpi = self.kpis.get("Mean Time To Resolution (MTTR)")
        availability_kpi = self.kpis.get("System Availability")
        automation_kpi = self.kpis.get("Automation Success Rate")
        
        return {
            "mttr": mttr_kpi.current_value if mttr_kpi else 0,
            "availability": availability_kpi.current_value if availability_kpi else 0,
            "automation_success": automation_kpi.current_value if automation_kpi else 0,
            "operational_health": "Excellent" if (mttr_kpi and mttr_kpi.current_value < 5) else "Good"
        }

async def demo_business_intelligence():
    """Demonstrate Business Intelligence Engine capabilities"""
    print("🏢 AIOps Business Intelligence Engine Demo")
    print("=" * 50)
    
    # Initialize BI Engine
    bi_engine = BusinessIntelligenceEngine()
    
    print("\n📊 Current KPI Status:")
    for name, kpi in bi_engine.kpis.items():
        status = "✅" if kpi.current_value >= kpi.target_value else "⚠️"
        trend_emoji = {"improving": "📈", "declining": "📉", "stable": "➡️", "volatile": "📊"}
        print(f"  {status} {name}: {kpi.current_value} {kpi.unit} {trend_emoji.get(kpi.trend.value, '❓')}")
    
    print("\n💰 Performing ROI Analysis...")
    
    # Sample ROI analyses
    roi_initiatives = [
        ("AIOps Platform Implementation", 250000, 45000, 12),
        ("Automated Incident Response", 75000, 18000, 6),
        ("Predictive Analytics System", 150000, 25000, 8),
        ("Security Automation Tools", 120000, 22000, 10)
    ]
    
    for initiative, investment, monthly_savings, duration in roi_initiatives:
        roi = await bi_engine.perform_roi_analysis(initiative, investment, monthly_savings, duration)
        print(f"  💡 {initiative}:")
        print(f"     ROI: {roi.roi_percentage:.1f}% | Payback: {roi.payback_period_months:.1f} months")
        print(f"     NPV: ${roi.net_present_value:,.0f} | Confidence: {roi.confidence_score:.1%}")
    
    print("\n🧠 Generating Strategic Insights...")
    insights = await bi_engine.generate_strategic_insights()
    
    for insight in insights[:3]:  # Show top 3 insights
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        print(f"  {priority_emoji.get(insight.priority, '⚪')} {insight.title}")
        print(f"     {insight.description}")
        print(f"     Impact: {insight.impact_score}/10 | Confidence: {insight.confidence:.1%}")
    
    print("\n📋 Executive Summary:")
    summary = await bi_engine.generate_executive_summary()
    print(f"  🎯 Overall Health Score: {summary.overall_health_score:.1f}/100")
    print(f"  📈 Key Achievements: {len(summary.key_achievements)} items")
    print(f"  ⚠️ Critical Issues: {len(summary.critical_issues)} items")
    print(f"  💰 Financial Impact: ${summary.financial_impact.get('net_benefit', 0):,.0f} net benefit")
    
    print("\n🌟 Key Achievements:")
    for achievement in summary.key_achievements[:3]:
        print(f"  ✅ {achievement}")
    
    if summary.critical_issues:
        print("\n⚠️ Critical Issues:")
        for issue in summary.critical_issues[:3]:
            print(f"  🔴 {issue}")
    
    print("\n🎯 Strategic Recommendations:")
    for rec in summary.strategic_recommendations[:3]:
        print(f"  💡 {rec}")
    
    print("\n📊 Dashboard Data Generated:")
    dashboard_data = await bi_engine.get_executive_dashboard_data()
    print(f"  📈 KPIs tracked: {len(dashboard_data.get('kpis', {}))}")
    print(f"  💰 ROI analyses: {len(dashboard_data.get('roi_analyses', []))}")
    print(f"  🧠 Strategic insights: {len(dashboard_data.get('strategic_insights', []))}")
    
    print("\n🏆 Business Intelligence Engine demonstration complete!")
    print("✨ Executive dashboards and ROI analytics fully operational!")

if __name__ == "__main__":
    asyncio.run(demo_business_intelligence())