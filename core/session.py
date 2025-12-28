"""
Session management: OrderItem, Session, and SessionStore.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
import uuid


@dataclass
class OrderItem:
    item_id: str
    name_ar: str
    quantity: int
    unit_price: float
    size: Optional[str] = None  # "صغير" | "وسط" | "كبير"
    notes: str = ""
    
    @property
    def total_price(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class Session:
    """Session state management"""
    
    # Identity
    session_id: str
    user_id: str
    started_at: datetime
    last_activity: datetime
    
    # Status
    status: str = "active"  # "active" | "completed" | "timeout"
    current_agent: str = "greeting"
    
    # Customer Info
    customer_name: Optional[str] = None
    
    # Intent & Mode
    intent: Optional[str] = None  # "delivery" | "pickup" | "complaint" | "inquiry"
    order_mode: str = "delivery"  # "delivery" | "pickup"
    
    # Location (for delivery) - Structured Address
    district: Optional[str] = None           # الحي (validated by check_delivery_district)
    street_name: Optional[str] = None        # اسم الشارع
    building_number: Optional[str] = None    # رقم المبنى / الفيلا
    additional_info: Optional[str] = None    # معلومات إضافية (اختياري)
    full_address: Optional[str] = None       # Combined full address string
    delivery_fee: float = 0
    estimated_time: Optional[str] = None
    location_confirmed: bool = False         # True after check_delivery_district succeeds
    address_complete: bool = False           # True after street + building collected
    
    # Customer contact (required for order confirmation)
    phone_number: Optional[str] = None
    address_confirmed: bool = False          # True after full address confirmed by user
    
    def build_full_address(self) -> str:
        """Build full address from structured parts."""
        parts = []
        if self.district:
            parts.append(f"حي {self.district}")
        if self.street_name:
            parts.append(self.street_name)
        if self.building_number:
            parts.append(f"مبنى/فيلا {self.building_number}")
        if self.additional_info:
            parts.append(f"({self.additional_info})")
        return "، ".join(parts) if parts else "غير محدد"
    
    # Order
    order_items: List[OrderItem] = field(default_factory=list)
    
    # Pending order items - structured list for better handling
    # Each item: {"text": str, "quantity": int, "processed": bool}
    pending_order_items: List[Dict] = field(default_factory=list)
    
    # Critical user constraints (allergies, dietary restrictions, etc.)
    # These are extracted from conversation and injected into ALL agent system prompts
    # to ensure they're never lost during handoffs
    constraints: List[str] = field(default_factory=list)
    
    # Conversation history (for SDK integration)
    conversation_history: List[dict] = field(default_factory=list)


    @property
    def conversation_state(self):
        """Get conversation state for this session."""
        from core.conversation_state import get_conversation_state
        return get_conversation_state(self.session_id)
    
    @property
    def subtotal(self) -> float:
        return sum(item.total_price for item in self.order_items)
    
    def add_constraint(self, constraint: str) -> None:
        """Add a critical constraint (e.g., allergy) that must persist across agents."""
        if constraint not in self.constraints:
            self.constraints.append(constraint)
    
    def get_constraints_prompt(self) -> str:
        """Format constraints for injection into agent system prompts."""
        if not self.constraints:
            return ""
        return "\n\n## ⚠️ قيود مهمة للعميل\n" + "\n".join(f"- {c}" for c in self.constraints)
    
    # Completion
    order_id: Optional[str] = None


class SessionStore:
    """
    In-memory session storage for local demo.
    
    LIMITATION: Sessions are lost on application restart.
    Production deployment would use Redis or a database for persistence.
    """
    _sessions: Dict[str, Session] = {}
    _current_session_id: Optional[str] = None  # Thread-local in production
    
    @classmethod
    def create(cls, user_id: str) -> Session:
        """Create a new session for a user."""
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        now = datetime.now()
        session = Session(
            session_id=session_id,
            user_id=user_id,
            started_at=now,
            last_activity=now
        )
        cls._sessions[session_id] = session
        cls._current_session_id = session_id
        return session
    
    @classmethod
    def get(cls, session_id: str) -> Optional[Session]:
        """Retrieve an existing session by ID."""
        session = cls._sessions.get(session_id)
        if session:
            session.last_activity = datetime.now()
        return session
    
    @classmethod
    def get_current(cls) -> Session:
        """Get the current session (for tool functions)."""
        if cls._current_session_id and cls._current_session_id in cls._sessions:
            return cls._sessions[cls._current_session_id]
        raise RuntimeError("No active session")
    
    @classmethod
    def set_current(cls, session_id: str) -> None:
        """Set the current session ID for this request context."""
        cls._current_session_id = session_id
    
    @classmethod
    def reset(cls) -> None:
        """Reset all sessions and create a fresh one. Used for testing."""
        cls._sessions.clear()
        cls._current_session_id = None
        # Create a new session
        cls.create("test_user")
    
    @classmethod
    def get_by_user(cls, user_id: str) -> Optional[Session]:
        """Find active session for a user (e.g., for WhatsApp message routing)."""
        for session in cls._sessions.values():
            if session.user_id == user_id and session.status == "active":
                return session
        return None
    
    @classmethod
    def cleanup_expired(cls, timeout_minutes: int = 10) -> int:
        """Remove sessions that have been inactive too long."""
        now = datetime.now()
        expired = []
        for session_id, session in cls._sessions.items():
            idle = (now - session.last_activity).total_seconds() / 60
            if idle > timeout_minutes:
                expired.append(session_id)
        for session_id in expired:
            del cls._sessions[session_id]
        return len(expired)

