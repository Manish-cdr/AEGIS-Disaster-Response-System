import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List
import time
import json
import os

# Try importing ultralytics; fall back to mock for environments without GPU
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("[WARN] ultralytics not installed. Using mock detection.")


class DisasterDetector:
    """Detects disaster-related objects and conditions using YOLO."""

    DISASTER_CLASSES = {
        "fire": ["fire", "flame", "smoke"],
        "flood": ["water", "flood", "boat", "person"],
        "accident": ["car", "truck", "motorcycle", "person", "bicycle"],
        "collapse": ["rubble", "debris", "person"],
        "general": ["person", "car", "truck", "bicycle", "motorcycle", "bus"]
    }

    SEVERITY_THRESHOLDS = {
        "LOW": 0.3,
        "MEDIUM": 0.5,
        "HIGH": 0.7,
        "CRITICAL": 0.85
    }

    def __init__(self, model_path: str = "yolov8n.pt"):
        self.model = None
        self.model_path = model_path

    def get_model(self):
        if self.model is None and YOLO_AVAILABLE:
            print("🔥 Loading YOLO model...")
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
        return self.model

    def _mock_detect(self, frame: np.ndarray) -> List[Dict]:
        """Mock detection for environments without YOLO."""
        import random
        mock_objects = [
            {"class": "person", "confidence": round(random.uniform(0.7, 0.95), 2),
             "bbox": [100, 100, 200, 300]},
            {"class": "car", "confidence": round(random.uniform(0.6, 0.90), 2),
             "bbox": [300, 150, 500, 280]},
        ]
        return mock_objects

    def detect_frame(self, frame: np.ndarray) -> List[Dict]:
        model = self.get_model()
        if model is None:
            return self._mock_detect(frame)
        results = model(frame, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                label = self.model.names[cls_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append({
                    "class": label,
                    "confidence": round(conf, 3),
                    "bbox": [x1, y1, x2, y2]
                })
        return detections

    def compute_severity(self, detections: List[Dict], disaster_type: str = "general") -> str:
        if not detections:
            return "LOW"
        avg_conf = np.mean([d["confidence"] for d in detections])
        person_count = sum(1 for d in detections if d["class"] == "person")
        score = avg_conf + (person_count * 0.05)
        score = min(score, 1.0)

        if score >= self.SEVERITY_THRESHOLDS["CRITICAL"]:
            return "CRITICAL"
        elif score >= self.SEVERITY_THRESHOLDS["HIGH"]:
            return "HIGH"
        elif score >= self.SEVERITY_THRESHOLDS["MEDIUM"]:
            return "MEDIUM"
        return "LOW"

    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        colors = {
            "person": (0, 255, 0),
            "car": (255, 165, 0),
            "fire": (0, 0, 255),
            "default": (255, 255, 0)
        }
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            label = det["class"]
            conf = det["confidence"]
            color = colors.get(label, colors["default"])
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label}: {conf:.2f}"
            cv2.putText(frame, text, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return frame


class VideoAnalyzer:
    """Main video analysis pipeline for disaster detection."""

    def __init__(self):
        self.detector = DisasterDetector()
        self.results_cache: Dict[str, Any] = {}

    def analyze_video(
        self,
        video_path: str,
        disaster_type: str = "general",
        sample_rate: int = 30,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze a video file for disaster-related content.

        Args:
            video_path: Path to the input video
            disaster_type: Type of disaster to focus on
            sample_rate: Analyze every Nth frame
            output_path: Optional path to save annotated output video

        Returns:
            Analysis results dictionary
        """
        video_path = Path(video_path)
        if not video_path.exists():
            return {"error": f"Video file not found: {video_path}"}

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"error": "Could not open video file"}

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0

        all_detections = []
        frame_results = []
        frame_idx = 0
        analyzed_frames = 0
        start_time = time.time()

        writer = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_rate == 0:
                detections = self.detector.detect_frame(frame)
                severity = self.detector.compute_severity(detections, disaster_type)
                frame_results.append({
                    "frame": frame_idx,
                    "timestamp": round(frame_idx / fps, 2) if fps > 0 else 0,
                    "detections": detections,
                    "severity": severity
                })
                all_detections.extend(detections)
                analyzed_frames += 1

                if writer:
                    annotated = self.detector.draw_detections(frame.copy(), detections)
                    writer.write(annotated)

            frame_idx += 1

        cap.release()
        if writer:
            writer.release()

        processing_time = round(time.time() - start_time, 2)

        # Aggregate stats
        class_counts: Dict[str, int] = {}
        for det in all_detections:
            cls = det["class"]
            class_counts[cls] = class_counts.get(cls, 0) + 1

        critical_frames = [f for f in frame_results if f["severity"] in ("HIGH", "CRITICAL")]
        overall_severity = "LOW"
        if frame_results:
            severity_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            worst = max(frame_results, key=lambda x: severity_order.index(x["severity"]))
            overall_severity = worst["severity"]

        result = {
            "video_info": {
                "path": str(video_path),
                "fps": round(fps, 2),
                "total_frames": total_frames,
                "analyzed_frames": analyzed_frames,
                "duration_seconds": round(duration, 2),
                "resolution": f"{width}x{height}"
            },
            "analysis": {
                "disaster_type": disaster_type,
                "overall_severity": overall_severity,
                "detected_objects": class_counts,
                "total_detections": len(all_detections),
                "critical_frame_count": len(critical_frames),
                "frame_results": frame_results[:20],  # limit for response size
            },
            "recommendations": self._generate_recommendations(overall_severity, class_counts, disaster_type),
            "processing_time_seconds": processing_time,
            "output_video": output_path if output_path else None
        }

        return result

    def _generate_recommendations(
        self, severity: str, objects: Dict[str, int], disaster_type: str
    ) -> List[str]:
        recs = []
        person_count = objects.get("person", 0)

        if severity == "CRITICAL":
            recs.append("🚨 CRITICAL: Immediate emergency response required!")
            recs.append("Dispatch all available rescue units to the location.")
        elif severity == "HIGH":
            recs.append("⚠️ HIGH RISK: Dispatch emergency teams immediately.")
        elif severity == "MEDIUM":
            recs.append("⚠️ MEDIUM RISK: Monitor situation and prepare response units.")
        else:
            recs.append("ℹ️ LOW RISK: Continue monitoring. No immediate action required.")

        if person_count > 0:
            recs.append(f"👥 {person_count} person(s) detected — prioritize evacuation assistance.")
        if disaster_type == "fire":
            recs.append("🔥 Fire scenario: Deploy fire suppression drone payload.")
        elif disaster_type == "flood":
            recs.append("🌊 Flood scenario: Deploy water rescue drone with flotation device.")
        elif disaster_type == "accident":
            recs.append("🚗 Accident scenario: Alert medical emergency services.")

        recs.append("🛸 Dispatch surveillance drone for real-time aerial monitoring.")
        return recs

    def extract_metadata(self, video_path: str) -> Dict[str, Any]:
        """Extract GPS/metadata from video file."""
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", video_path],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                tags = data.get("format", {}).get("tags", {})
                location = tags.get("location", tags.get("com.apple.quicktime.location.ISO6709", None))
                return {
                    "raw_metadata": tags,
                    "gps_location": location,
                    "has_gps": location is not None
                }
        except Exception:
            pass
        return {"raw_metadata": {}, "gps_location": None, "has_gps": False}