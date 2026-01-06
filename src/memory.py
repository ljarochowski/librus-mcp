"""Memory and trend tracking"""
from typing import Dict
from .storage import load_memory, save_memory


async def update_memory(child_name: str, raw_data: Dict):
    """
    Update memory with new scraped data.
    
    Tracks grade history and other trends.
    """
    memory = load_memory(child_name)
    
    # Update grade history
    grade_history = memory.setdefault("grade_history", {})
    
    for grade in raw_data.get("grades", []):
        subject = grade["subject"]
        if subject not in grade_history:
            grade_history[subject] = []
        
        grade_entry = {
            "grade": grade["grade"],
            "date": grade["date"],
            "category": grade["category"],
            "weight": grade["weight"]
        }
        
        # Avoid duplicates
        if grade_entry not in grade_history[subject]:
            grade_history[subject].append(grade_entry)
    
    save_memory(child_name, memory)


def format_memory(memory: Dict) -> str:
    """Format memory as readable text"""
    lines = [
        f"# Memory for {memory.get('child_name', 'Unknown')}",
        "",
        f"**Last updated:** {memory.get('last_updated', 'Never')}",
        ""
    ]
    
    # Issues
    issues = memory.get("issues", [])
    if issues:
        lines.append("## 🔴 Issues")
        lines.append("")
        for issue in issues[-5:]:  # Last 5
            lines.append(f"- {issue['content']} ({issue['timestamp']})")
        lines.append("")
    
    # Action items
    action_items = memory.get("action_items", [])
    if action_items:
        lines.append("## ✅ Action Items")
        lines.append("")
        for item in action_items[-5:]:
            lines.append(f"- {item['content']} ({item['timestamp']})")
        lines.append("")
    
    # Parent notes
    parent_notes = memory.get("parent_notes", [])
    if parent_notes:
        lines.append("## 📝 Parent Notes")
        lines.append("")
        for note in parent_notes[-5:]:
            lines.append(f"- {note['content']} ({note['timestamp']})")
        lines.append("")
    
    # Grade history summary
    grade_history = memory.get("grade_history", {})
    if grade_history:
        lines.append("## 📊 Grade History")
        lines.append("")
        for subject, grades in grade_history.items():
            lines.append(f"### {subject}")
            recent_grades = grades[-5:]  # Last 5 grades
            for g in recent_grades:
                lines.append(f"- {g['grade']} ({g['category']}, weight: {g['weight']}) - {g['date']}")
            lines.append("")
    
    # Trends
    trends = memory.get("trends", {})
    if trends:
        lines.append("## 📈 Trends")
        lines.append("")
        for key, value in trends.items():
            lines.append(f"- **{key}:** {value}")
        lines.append("")
    
    return "\n".join(lines)
