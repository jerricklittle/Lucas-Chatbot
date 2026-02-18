from datetime import datetime
from typing import Dict, Optional


class Question_Timer:
    """
    Tracks time spent on survey questions for paradata collection.
    
    Handles:
    - Starting/stopping timers on navigation
    - Accumulating time if user returns to a question
    - Pausing when leaving a question
    """
    
    def __init__(self):
        self.start_times: Dict[str, datetime] = {}  # question_id -> start timestamp
        self.accumulated_times: Dict[str, float] = {}  # question_id -> total seconds
        self.current_question_id: Optional[str] = None
        
    def start_question(self, question_id: str):
        """
        Start timing for a question.
        If returning to a question, resume timing.
        """
        # Stop timing for previous question if any
        if self.current_question_id:
            self._pause_current()
        
        # Start timing for new question
        self.current_question_id = question_id
        self.start_times[question_id] = datetime.now()
        
        # Initialize accumulated time if first visit
        if question_id not in self.accumulated_times:
            self.accumulated_times[question_id] = 0.0
            print(f"⏱️  TIMER: Started tracking '{question_id}' (first visit)")
        else:
            print(f"⏱️  TIMER: Resumed '{question_id}' (accumulated: {self.accumulated_times[question_id]:.2f}s)")

    
    def _pause_current(self):
        """Stop timing the current question and accumulate the time"""
        if not self.current_question_id:
            return
        
        question_id = self.current_question_id
        if question_id in self.start_times:
            elapsed = (datetime.now() - self.start_times[question_id]).total_seconds()
            self.accumulated_times[question_id] = self.accumulated_times.get(question_id, 0.0) + elapsed
            print(f"⏸️  TIMER: Paused '{question_id}' (+{elapsed:.2f}s, total: {self.accumulated_times[question_id]:.2f}s)")
            del self.start_times[question_id]
    
    def stop_all(self):
        """Stop timing everything (called on survey completion)"""
        print(f"\n🛑 TIMER: Stopping all timers...")
        self._pause_current()
        self.current_question_id = None
        print(f"✅ TIMER: All timers stopped\n")
    
    def get_time_for_question(self, question_id: str) -> float:
        """
        Get total time spent on a question in seconds.
        Includes currently active time if this is the current question.
        """
        total = self.accumulated_times.get(question_id, 0.0)
        
        # Add current session time if this question is active
        if question_id == self.current_question_id and question_id in self.start_times:
            current_elapsed = (datetime.now() - self.start_times[question_id]).total_seconds()
            total += current_elapsed
        
        return total
    
    def get_all_times(self) -> Dict[str, float]:
        """
        Get dictionary of all question times.
        Finalizes current question timing if active.
        """
        # Finalize current timing
        if self.current_question_id:
            self._pause_current()
        
        print(f"\n📊 TIMER: Final timing summary:")
        print(f"{'Question ID':<20} {'Time Spent':<15}")
        print(f"{'-'*35}")
        for q_id, time_sec in sorted(self.accumulated_times.items()):
            print(f"{q_id:<20} {time_sec:>10.2f}s")
        print(f"{'-'*35}")
        total_time = sum(self.accumulated_times.values())
        print(f"{'TOTAL':<20} {total_time:>10.2f}s\n")
        
        return self.accumulated_times.copy()
    
    def reset(self):
        """Reset all timing data (for new survey response)"""
        self.start_times.clear()
        self.accumulated_times.clear()
        self.current_question_id = None