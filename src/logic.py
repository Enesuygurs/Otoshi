import time
import threading
import pickle
from typing import List, Dict, Any, Callable, Optional
from pynput.mouse import Controller as MouseController, Listener as MouseListener, Button
from pynput.keyboard import Controller as KeyboardController, Listener as KeyboardListener

class MacroEngine:
    """
    Core engine responsible for recording and playing back mouse and keyboard events.
    """
    def __init__(self):
        self.mouse_ctrl = MouseController()
        self.keyboard_ctrl = KeyboardController()
        self.events: List[Dict[str, Any]] = []
        self.is_recording = False
        self.is_playing = False
        self.start_time = 0.0
        self.playback_speed = 1.0
        
        self.m_listener: Optional[MouseListener] = None
        self.k_listener: Optional[KeyboardListener] = None

    def start_recording(self, on_move: Callable, on_click: Callable, on_scroll: Callable, 
                        on_press: Callable, on_release: Callable) -> bool:
        """
        Starts listening to mouse and keyboard events.
        """
        if self.is_playing:
            return False
            
        self.is_recording = True
        self.events = []
        self.start_time = time.time()
        
        self.m_listener = MouseListener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        self.k_listener = KeyboardListener(on_press=on_press, on_release=on_release)
        
        self.m_listener.start()
        self.k_listener.start()
        return True

    def stop_recording(self) -> None:
        """
        Stops the event listeners.
        """
        if not self.is_recording:
            return
        self.is_recording = False
        if self.m_listener:
            self.m_listener.stop()
        if self.k_listener:
            self.k_listener.stop()

    def play_macro(self, loop_count: int, on_finish_callback: Callable) -> None:
        """
        Plays back the recorded events in a separate thread.
        """
        if self.is_recording or not self.events:
            return
            
        self.is_playing = True
        threading.Thread(target=self._play_loop, args=(loop_count, on_finish_callback,), daemon=True).start()

    def stop_playback(self) -> None:
        """
        Signals the playback loop to stop.
        """
        self.is_playing = False

    def _play_loop(self, loop_count: int, on_finish_callback: Callable) -> None:
        """
        Internal loop for macro playback.
        """
        current_loop = 0
        while self.is_playing:
            if loop_count > 0 and current_loop >= loop_count:
                break
                
            start_time = time.time()
            for event in self.events:
                if not self.is_playing:
                    break
                    
                action_time = event['time'] / self.playback_speed
                elapsed = time.time() - start_time
                if action_time > elapsed:
                    time.sleep(action_time - elapsed)
                    
                try:
                    if event['type'] == 'move':
                        self.mouse_ctrl.position = event['pos']
                    elif event['type'] == 'click':
                        if event['pressed']:
                            self.mouse_ctrl.position = event['pos']
                            self.mouse_ctrl.press(event['button'])
                        else:
                            self.mouse_ctrl.release(event['button'])
                    elif event['type'] == 'scroll':
                        self.mouse_ctrl.position = event['pos']
                        self.mouse_ctrl.scroll(event['dx'], event['dy'])
                    elif event['type'] == 'keypress':
                        self.keyboard_ctrl.press(event['key'])
                    elif event['type'] == 'keyrelease':
                        self.keyboard_ctrl.release(event['key'])
                except Exception:
                    # Ignore playback errors for individual events to prevent crash
                    pass
            
            current_loop += 1
            if not self.is_playing:
                break

        self.is_playing = False
        on_finish_callback()

    def save_to_file(self, file_path: str) -> None:
        """
        Serializes events to a file.
        """
        with open(file_path, "wb") as f:
            pickle.dump(self.events, f)

    def load_from_file(self, file_path: str) -> int:
        """
        Loads serialized events from a file.
        """
        with open(file_path, "rb") as f:
            self.events = pickle.load(f)
        return len(self.events)


class AutoClickerEngine:
    """
    Engine responsible for automated clicking at fixed intervals.
    """
    def __init__(self):
        self.mouse_ctrl = MouseController()
        self.is_running = False
        self.thread: Optional[threading.Thread] = None

    def start(self, interval_ms: int, button_str: str, click_type: str, 
              click_times: int, loc_type: str, loc_x: int = 0, loc_y: int = 0, 
              on_stop_callback: Optional[Callable] = None) -> None:
        """
        Starts the auto-clicking loop in a separate thread.
        """
        if self.is_running:
            return
            
        self.is_running = True
        self.thread = threading.Thread(
            target=self._loop, 
            args=(interval_ms, button_str, click_type, click_times, loc_type, loc_x, loc_y, on_stop_callback),
            daemon=True
        )
        self.thread.start()

    def stop(self) -> None:
        """
        Stops the auto-clicking loop.
        """
        self.is_running = False

    def _loop(self, interval_ms: int, button_str: str, click_type: str, 
              click_times: int, loc_type: str, loc_x: int, loc_y: int, 
              on_stop_callback: Optional[Callable]) -> None:
        """
        Internal auto-clicking loop.
        """
        btn_map = {
            "Left": Button.left,
            "Right": Button.right,
            "Middle": Button.middle
        }
        
        btn = btn_map.get(button_str, Button.left)
        clicks = 2 if click_type == "Double" else 1
        interval = max(0.001, interval_ms / 1000.0)

        click_count = 0
        target_times = click_times

        while self.is_running:
            if target_times > 0 and click_count >= target_times:
                self.is_running = False
                if on_stop_callback:
                    on_stop_callback()
                break

            if loc_type == "Fixed":
                self.mouse_ctrl.position = (loc_x, loc_y)
                
            try:
                self.mouse_ctrl.click(btn, clicks)
            except Exception:
                pass
                
            click_count += 1
            time.sleep(interval)
