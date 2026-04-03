"""
Community Help Center Integration
Ticketing system, live chat, and community forum features for AIOps dashboard
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

class TicketPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class TicketStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_RESPONSE = "waiting_response"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketCategory(Enum):
    SYSTEM_ISSUE = "system_issue"
    PERFORMANCE = "performance"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    GENERAL_HELP = "general_help"

@dataclass
class Ticket:
    id: str
    title: str
    description: str
    category: str
    priority: str
    status: str
    user_id: str
    user_email: str
    created_at: str
    updated_at: str
    assigned_to: Optional[str] = None
    tags: List[str] = None
    system_info: Optional[Dict] = None

@dataclass
class ChatMessage:
    id: str
    ticket_id: str
    user_id: str
    user_name: str
    message: str
    timestamp: str
    is_agent: bool = False
    attachments: List[str] = None

@dataclass
class KnowledgeBaseArticle:
    id: str
    title: str
    content: str
    category: str
    tags: List[str]
    created_at: str
    updated_at: str
    author_id: str
    view_count: int = 0
    helpful_votes: int = 0

@dataclass
class CommunityPost:
    id: str
    title: str
    content: str
    author_id: str
    author_name: str
    category: str
    created_at: str
    updated_at: str
    votes: int = 0
    replies_count: int = 0
    tags: List[str] = None
    is_solved: bool = False

class CommunityHelpCenter:
    def __init__(self, db_path: str = "community_help.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Apply schema migrations for the community help center SQLite database."""
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _migrations_dir = _os.path.join(
            _here, "..", "..", "migrations", "sqlite", "community"
        )
        from app.core.sqlite_migrator import run_sqlite_migrations
        run_sqlite_migrations(self.db_path, _migrations_dir)
    
    # Ticket Management
    def create_ticket(self, title: str, description: str, category: TicketCategory, 
                     priority: TicketPriority, user_id: str, user_email: str,
                     system_info: Optional[Dict] = None, tags: List[str] = None) -> Ticket:
        """Create a new support ticket"""
        ticket_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        ticket = Ticket(
            id=ticket_id,
            title=title,
            description=description,
            category=category.value,
            priority=priority.value,
            status=TicketStatus.OPEN.value,
            user_id=user_id,
            user_email=user_email,
            created_at=now,
            updated_at=now,
            tags=tags or [],
            system_info=system_info
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tickets 
            (id, title, description, category, priority, status, user_id, user_email, 
             tags, system_info, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ticket.id, ticket.title, ticket.description, ticket.category,
            ticket.priority, ticket.status, ticket.user_id, ticket.user_email,
            json.dumps(ticket.tags), json.dumps(ticket.system_info),
            ticket.created_at, ticket.updated_at
        ))
        
        conn.commit()
        conn.close()
        
        return ticket
    
    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        """Get ticket by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_ticket(row)
        return None
    
    def update_ticket_status(self, ticket_id: str, status: TicketStatus, assigned_to: Optional[str] = None):
        """Update ticket status and assignment"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        if assigned_to:
            cursor.execute('''
                UPDATE tickets 
                SET status = ?, assigned_to = ?, updated_at = ?
                WHERE id = ?
            ''', (status.value, assigned_to, now, ticket_id))
        else:
            cursor.execute('''
                UPDATE tickets 
                SET status = ?, updated_at = ?
                WHERE id = ?
            ''', (status.value, now, ticket_id))
        
        conn.commit()
        conn.close()
    
    def get_user_tickets(self, user_id: str, status: Optional[TicketStatus] = None) -> List[Ticket]:
        """Get all tickets for a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if status:
            cursor.execute('''
                SELECT * FROM tickets 
                WHERE user_id = ? AND status = ?
                ORDER BY created_at DESC
            ''', (user_id, status.value))
        else:
            cursor.execute('''
                SELECT * FROM tickets 
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_ticket(row) for row in rows]
    
    def get_tickets_by_priority(self, priority: TicketPriority) -> List[Ticket]:
        """Get tickets by priority level"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM tickets 
            WHERE priority = ? AND status NOT IN ('resolved', 'closed')
            ORDER BY created_at ASC
        ''', (priority.value,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_ticket(row) for row in rows]
    
    # Live Chat System
    def add_chat_message(self, ticket_id: str, user_id: str, user_name: str, 
                        message: str, is_agent: bool = False, attachments: List[str] = None) -> ChatMessage:
        """Add a chat message to a ticket"""
        message_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        chat_message = ChatMessage(
            id=message_id,
            ticket_id=ticket_id,
            user_id=user_id,
            user_name=user_name,
            message=message,
            timestamp=now,
            is_agent=is_agent,
            attachments=attachments or []
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO chat_messages 
            (id, ticket_id, user_id, user_name, message, timestamp, is_agent, attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            chat_message.id, chat_message.ticket_id, chat_message.user_id,
            chat_message.user_name, chat_message.message, chat_message.timestamp,
            chat_message.is_agent, json.dumps(chat_message.attachments)
        ))
        
        conn.commit()
        conn.close()
        
        return chat_message
    
    def get_chat_messages(self, ticket_id: str) -> List[ChatMessage]:
        """Get all chat messages for a ticket"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM chat_messages 
            WHERE ticket_id = ?
            ORDER BY timestamp ASC
        ''', (ticket_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_chat_message(row) for row in rows]
    
    # Knowledge Base
    def create_knowledge_article(self, title: str, content: str, category: str,
                               author_id: str, tags: List[str] = None) -> KnowledgeBaseArticle:
        """Create a new knowledge base article"""
        article_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        article = KnowledgeBaseArticle(
            id=article_id,
            title=title,
            content=content,
            category=category,
            tags=tags or [],
            author_id=author_id,
            created_at=now,
            updated_at=now
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO knowledge_base 
            (id, title, content, category, tags, author_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            article.id, article.title, article.content, article.category,
            json.dumps(article.tags), article.author_id, article.created_at, article.updated_at
        ))
        
        conn.commit()
        conn.close()
        
        return article
    
    def search_knowledge_base(self, query: str, category: Optional[str] = None) -> List[KnowledgeBaseArticle]:
        """Search knowledge base articles"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if category:
            cursor.execute('''
                SELECT * FROM knowledge_base 
                WHERE (title LIKE ? OR content LIKE ?) AND category = ?
                ORDER BY helpful_votes DESC, view_count DESC
            ''', (f'%{query}%', f'%{query}%', category))
        else:
            cursor.execute('''
                SELECT * FROM knowledge_base 
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY helpful_votes DESC, view_count DESC
            ''', (f'%{query}%', f'%{query}%'))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_kb_article(row) for row in rows]
    
    def increment_article_views(self, article_id: str):
        """Increment view count for an article"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE knowledge_base 
            SET view_count = view_count + 1
            WHERE id = ?
        ''', (article_id,))
        
        conn.commit()
        conn.close()
    
    def vote_helpful(self, article_id: str):
        """Vote an article as helpful"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE knowledge_base 
            SET helpful_votes = helpful_votes + 1
            WHERE id = ?
        ''', (article_id,))
        
        conn.commit()
        conn.close()
    
    # Community Forum
    def create_community_post(self, title: str, content: str, author_id: str,
                            author_name: str, category: str, tags: List[str] = None) -> CommunityPost:
        """Create a new community forum post"""
        post_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        post = CommunityPost(
            id=post_id,
            title=title,
            content=content,
            author_id=author_id,
            author_name=author_name,
            category=category,
            created_at=now,
            updated_at=now,
            tags=tags or []
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO community_posts 
            (id, title, content, author_id, author_name, category, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            post.id, post.title, post.content, post.author_id, post.author_name,
            post.category, json.dumps(post.tags), post.created_at, post.updated_at
        ))
        
        conn.commit()
        conn.close()
        
        return post
    
    def get_community_posts(self, category: Optional[str] = None, limit: int = 20) -> List[CommunityPost]:
        """Get community posts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if category:
            cursor.execute('''
                SELECT * FROM community_posts 
                WHERE category = ?
                ORDER BY votes DESC, created_at DESC
                LIMIT ?
            ''', (category, limit))
        else:
            cursor.execute('''
                SELECT * FROM community_posts 
                ORDER BY votes DESC, created_at DESC
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_community_post(row) for row in rows]
    
    def vote_post(self, post_id: str, upvote: bool = True):
        """Vote on a community post"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if upvote:
            cursor.execute('''
                UPDATE community_posts 
                SET votes = votes + 1
                WHERE id = ?
            ''', (post_id,))
        else:
            cursor.execute('''
                UPDATE community_posts 
                SET votes = votes - 1
                WHERE id = ?
            ''', (post_id,))
        
        conn.commit()
        conn.close()
    
    def mark_post_solved(self, post_id: str):
        """Mark a community post as solved"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE community_posts 
            SET is_solved = TRUE, updated_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), post_id))
        
        conn.commit()
        conn.close()
    
    # Analytics and Reporting
    def get_ticket_analytics(self) -> Dict:
        """Get ticket analytics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total tickets by status
        cursor.execute('''
            SELECT status, COUNT(*) 
            FROM tickets 
            GROUP BY status
        ''')
        status_counts = dict(cursor.fetchall())
        
        # Tickets by priority
        cursor.execute('''
            SELECT priority, COUNT(*) 
            FROM tickets 
            WHERE status NOT IN ('resolved', 'closed')
            GROUP BY priority
        ''')
        priority_counts = dict(cursor.fetchall())
        
        # Tickets by category
        cursor.execute('''
            SELECT category, COUNT(*) 
            FROM tickets 
            GROUP BY category
        ''')
        category_counts = dict(cursor.fetchall())
        
        # Average resolution time (for resolved tickets)
        cursor.execute('''
            SELECT AVG(CAST((julianday(updated_at) - julianday(created_at)) * 24 AS REAL)) as avg_hours
            FROM tickets 
            WHERE status = 'resolved'
        ''')
        avg_resolution_time = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_tickets': sum(status_counts.values()),
            'status_breakdown': status_counts,
            'priority_breakdown': priority_counts,
            'category_breakdown': category_counts,
            'avg_resolution_time_hours': round(avg_resolution_time, 2)
        }
    
    def get_popular_articles(self, limit: int = 10) -> List[KnowledgeBaseArticle]:
        """Get most popular knowledge base articles"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM knowledge_base 
            ORDER BY view_count DESC, helpful_votes DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_kb_article(row) for row in rows]
    
    # Helper methods
    def _row_to_ticket(self, row) -> Ticket:
        """Convert database row to Ticket object"""
        return Ticket(
            id=row[0],
            title=row[1],
            description=row[2],
            category=row[3],
            priority=row[4],
            status=row[5],
            user_id=row[6],
            user_email=row[7],
            assigned_to=row[8],
            tags=json.loads(row[9]) if row[9] else [],
            system_info=json.loads(row[10]) if row[10] else None,
            created_at=row[11],
            updated_at=row[12]
        )
    
    def _row_to_chat_message(self, row) -> ChatMessage:
        """Convert database row to ChatMessage object"""
        return ChatMessage(
            id=row[0],
            ticket_id=row[1],
            user_id=row[2],
            user_name=row[3],
            message=row[4],
            timestamp=row[5],
            is_agent=bool(row[6]),
            attachments=json.loads(row[7]) if row[7] else []
        )
    
    def _row_to_kb_article(self, row) -> KnowledgeBaseArticle:
        """Convert database row to KnowledgeBaseArticle object"""
        return KnowledgeBaseArticle(
            id=row[0],
            title=row[1],
            content=row[2],
            category=row[3],
            tags=json.loads(row[4]) if row[4] else [],
            author_id=row[5],
            view_count=row[6],
            helpful_votes=row[7],
            created_at=row[8],
            updated_at=row[9]
        )
    
    def _row_to_community_post(self, row) -> CommunityPost:
        """Convert database row to CommunityPost object"""
        return CommunityPost(
            id=row[0],
            title=row[1],
            content=row[2],
            author_id=row[3],
            author_name=row[4],
            category=row[5],
            votes=row[6],
            replies_count=row[7],
            tags=json.loads(row[8]) if row[8] else [],
            is_solved=bool(row[9]),
            created_at=row[10],
            updated_at=row[11]
        )

# Integration with main dashboard
class CommunityDashboardIntegration:
    def __init__(self, help_center: CommunityHelpCenter):
        self.help_center = help_center
    
    def get_dashboard_widget_data(self, user_id: str) -> Dict:
        """Get community data for dashboard widgets"""
        user_tickets = self.help_center.get_user_tickets(user_id)
        open_tickets = [t for t in user_tickets if t.status in ['open', 'in_progress']]
        
        return {
            'open_tickets_count': len(open_tickets),
            'recent_tickets': user_tickets[:3],
            'urgent_tickets': [t for t in open_tickets if t.priority == 'critical'],
            'knowledge_suggestions': self.help_center.get_popular_articles(3)
        }
    
    def create_auto_ticket_from_alert(self, alert_data: Dict, user_id: str, user_email: str) -> Ticket:
        """Automatically create a ticket from system alert"""
        title = f"System Alert: {alert_data.get('type', 'Unknown Issue')}"
        description = f"""
        Automatic ticket created from system alert:
        
        Alert Type: {alert_data.get('type')}
        Severity: {alert_data.get('severity')}
        Timestamp: {alert_data.get('timestamp')}
        
        Details:
        {alert_data.get('message', 'No additional details available')}
        """
        
        # Determine priority based on alert severity
        priority_map = {
            'critical': TicketPriority.CRITICAL,
            'high': TicketPriority.HIGH,
            'medium': TicketPriority.MEDIUM,
            'low': TicketPriority.LOW
        }
        
        priority = priority_map.get(alert_data.get('severity', 'medium'), TicketPriority.MEDIUM)
        
        return self.help_center.create_ticket(
            title=title,
            description=description,
            category=TicketCategory.SYSTEM_ISSUE,
            priority=priority,
            user_id=user_id,
            user_email=user_email,
            system_info=alert_data
        )

# Pre-populate with sample knowledge base articles
def populate_sample_data(help_center: CommunityHelpCenter):
    """Populate the help center with sample data"""
    
    # Sample KB articles
    articles = [
        {
            'title': 'How to Optimize CPU Performance',
            'content': '''
# CPU Performance Optimization Guide

## Understanding CPU Usage
High CPU usage can indicate:
- Too many running processes
- Resource-intensive applications
- Background system tasks

## Quick Solutions
1. **Close unnecessary applications**
   - Check Task Manager for high CPU processes
   - End non-essential tasks

2. **Restart your system**
   - Clears temporary processes
   - Resets system state

3. **Update drivers**
   - Ensure latest graphics and system drivers
   - Use Windows Update or manufacturer tools

## Advanced Troubleshooting
- Disable startup programs
- Check for malware
- Monitor temperature levels
- Consider hardware upgrades
            ''',
            'category': 'performance',
            'tags': ['cpu', 'performance', 'optimization']
        },
        {
            'title': 'Memory Management Best Practices',
            'content': '''
# Memory Management Guide

## Understanding Memory Usage
Memory issues can cause:
- System slowdowns
- Application crashes
- Poor performance

## Quick Fixes
1. **Close browser tabs**
   - Each tab consumes memory
   - Use bookmark management

2. **Restart applications**
   - Clears memory leaks
   - Refreshes application state

3. **Check available RAM**
   - Monitor memory usage patterns
   - Identify memory-hungry processes

## Long-term Solutions
- Upgrade RAM capacity
- Use memory optimization tools
- Regular system maintenance
            ''',
            'category': 'performance',
            'tags': ['memory', 'ram', 'optimization']
        }
    ]
    
    for article_data in articles:
        help_center.create_knowledge_article(
            title=article_data['title'],
            content=article_data['content'],
            category=article_data['category'],
            author_id='system',
            tags=article_data['tags']
        )

if __name__ == "__main__":
    # Demo usage
    help_center = CommunityHelpCenter()
    populate_sample_data(help_center)
    
    # Create sample ticket
    ticket = help_center.create_ticket(
        title="High CPU Usage Alert",
        description="CPU usage has been consistently above 90% for the past hour",
        category=TicketCategory.SYSTEM_ISSUE,
        priority=TicketPriority.HIGH,
        user_id="user123",
        user_email="user@example.com",
        system_info={'cpu': 95, 'memory': 78, 'timestamp': datetime.now().isoformat()}
    )
    
    print(f"✅ Created ticket: {ticket.id}")
    
    # Add chat message
    message = help_center.add_chat_message(
        ticket_id=ticket.id,
        user_id="user123",
        user_name="John Doe",
        message="I've tried restarting the application but the issue persists."
    )
    
    print(f"💬 Added chat message: {message.id}")
    
    # Search knowledge base
    articles = help_center.search_knowledge_base("CPU performance")
    print(f"📚 Found {len(articles)} knowledge base articles")
    
    # Get analytics
    analytics = help_center.get_ticket_analytics()
    print(f"📊 Ticket analytics: {analytics}")