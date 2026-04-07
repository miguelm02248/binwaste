import time
import os
import cv2
import numpy as np
from datetime import datetime
from inference_sdk import InferenceHTTPClient

# Global variables for motion detection
frame_count = 0
capture_triggered = False
classification_in_progress = False
background_subtractor = None
motion_threshold = 5000  # Minimum area of motion to trigger capture
min_motion_frames = 5  # Number of consecutive frames with motion required
motion_frame_count = 0
last_capture_time = 0
capture_cooldown = 5.0  # seconds between captures
motion_detected_time = 0
capture_delay = 1.0  # seconds to wait after motion before capturing

def capture_and_analyze(frame):
    """
    Save the current frame and run classification inference
    """
    global frame_count, classification_in_progress
    
    frame_count += 1
    classification_in_progress = True
    
    # Create images directory if it doesn't exist
    if not os.path.exists('detected_images'):
        os.makedirs('detected_images')
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"detected_images/detection_{timestamp}_{frame_count}.jpg"
    
    try:
        print(f"\n📸 Capturing image...")
        
        # Save the current frame
        cv2.imwrite(filename, frame)
        print(f"✅ Picture saved: {filename}")
        
        # Run classification inference immediately on the captured image
        print("🔄 Running classification inference on captured image...")
        
        # Initialize the HTTP client
        client = InferenceHTTPClient(
            api_url="https://serverless.roboflow.com",
            api_key="Mqg6MjfPG888hkIAilqR"
        )
        
        # Run the workflow on the captured image
        result = client.run_workflow(
            workspace_name="smartsort-vfpxc",
            # workflow_id="smartsort-classify-v1",
            #alternative models
                # workflow_id="smartsort-classify-simple-v2",
                workflow_id="smartsort-classify-simple-v3",
                #workflow_id="smartsort-classify-simple-v4",
            images={
                "image": filename
            },
            use_cache=True  # cache workflow definition for 15 minutes
        )
        
        if result:
            print(f"📦 Classification Results for {filename}:")
            
            # Parse the result - get the first prediction
            if isinstance(result, list) and len(result) > 0:
                # Handle list format (workflow result)
                model_predictions = result[0].get('model_predictions', {})
                predictions = model_predictions.get('predictions', [])
                
                if predictions:
                    first_prediction = predictions[0]
                    class_name = first_prediction.get('class', 'Unknown')
                    confidence = first_prediction.get('confidence', 0)
                    confidence_pct = confidence * 100 if isinstance(confidence, (int, float)) else confidence
                    
                    print(f"   🎯 {class_name} (confidence: {confidence_pct:.1f}%)")
                else:
                    print("   ❌ No predictions found")
            elif isinstance(result, dict):
                # Handle dict format
                if 'predictions' in result:
                    predictions = result['predictions']
                    if predictions:
                        first_prediction = predictions[0]
                        class_name = first_prediction.get('class', first_prediction.get('class_name', 'Unknown'))
                        confidence = first_prediction.get('confidence', 0)
                        confidence_pct = confidence * 100 if isinstance(confidence, (int, float)) else confidence
                        
                        print(f"   🎯 {class_name} (confidence: {confidence_pct:.1f}%)")
                    else:
                        print("   ❌ No predictions found")
                else:
                    print(f"   ❌ Unexpected result format: {result}")
            else:
                print(f"   ❌ Unexpected result type: {type(result)}")
        else:
            print("❌ No classification results for captured image")
        
        # Classification complete, reset flag
        classification_in_progress = False
        return True
        
    except Exception as e:
        print(f"❌ Error capturing/analyzing image: {e}")
        classification_in_progress = False
        return False

def detect_motion(frame):
    """
    Detect motion in the frame using background subtraction
    """
    global background_subtractor, motion_frame_count, motion_threshold, min_motion_frames
    
    # Initialize background subtractor if not already done
    if background_subtractor is None:
        background_subtractor = cv2.createBackgroundSubtractorMOG2(
            detectShadows=True,
            varThreshold=50,
            history=500
        )
        return False, 0
    
    # Apply background subtraction
    fg_mask = background_subtractor.apply(frame)
    
    # Remove noise with morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    
    # Find contours of motion
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Calculate total motion area
    motion_area = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > 100:  # Filter out small noise
            motion_area += area
    
    # Check if motion is significant enough
    if motion_area > motion_threshold:
        motion_frame_count += 1
        if motion_frame_count >= min_motion_frames:
            motion_frame_count = 0  # Reset counter
            return True, motion_area
    else:
        motion_frame_count = 0  # Reset counter if no motion
    
    return False, motion_area

def motion_detection_loop():
    """
    Main motion detection loop using OpenCV
    """
    global capture_triggered, last_capture_time, capture_cooldown, motion_detected_time, capture_delay, classification_in_progress
    
    # Initialize webcam
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Error: Could not open webcam")
        return
    
    # Set camera resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    print("🎥 Starting motion detection...")
    print("💡 Press 'q' to quit, or Ctrl+C to stop")
    
    # Give camera time to adjust and learn background
    print("🔄 Learning background (5 seconds)...")
    for i in range(150):  # ~5 seconds at 30fps
        ret, frame = cap.read()
        if ret:
            detect_motion(frame)  # Initialize background model
        time.sleep(0.033)  # ~30fps
    
    print("✅ Background learning complete! Motion detection active.")
    
    try:
        while True:
            current_time = time.time()
            
            # Check cooldown period
            if current_time - last_capture_time < capture_cooldown:
                print(f"\r⏳ Cooldown: {capture_cooldown - (current_time - last_capture_time):.1f}s remaining", end="", flush=True)
                time.sleep(0.1)
                continue
            
            # Skip motion detection if classification is in progress
            if classification_in_progress:
                print(f"\r🔄 Classification in progress...", end="", flush=True)
                time.sleep(0.5)  # Longer sleep to reduce CPU usage
                continue
            
            # Read frame from webcam only when not in classification
            ret, frame = cap.read()
            if not ret:
                print("❌ Error: Could not read frame from webcam")
                break
            
            # Detect motion
            motion_detected, motion_area = detect_motion(frame)
            
            if motion_detected and not capture_triggered and not classification_in_progress and motion_detected_time == 0:
                # First time motion is detected - start countdown
                motion_detected_time = current_time
                print(f"\n🔍 Motion detected! Area: {motion_area:.0f} pixels")
                print(f"⏳ Waiting {capture_delay} seconds before capture...")
            elif motion_detected_time != 0 and not capture_triggered and not classification_in_progress:
                # Check if capture delay has passed
                if current_time - motion_detected_time >= capture_delay:
                    print(f"\n📸 Capture delay complete! Triggering capture...")
                    
                    # Set flag to prevent multiple captures
                    capture_triggered = True
                    last_capture_time = current_time
                    motion_detected_time = 0  # Reset motion detection time
                    
                    # Capture and analyze using current frame
                    success = capture_and_analyze(frame)
                    
                    if success:
                        print(f"✅ Automatic capture and analysis completed!")
                        print(f"⏳ Cooldown: {capture_cooldown} seconds before next detection...")
                    else:
                        print("❌ Automatic capture failed!")
                    
                    print("=" * 50)
                    
                    # Reset flag
                    capture_triggered = False
                else:
                    # Still in capture delay period - show countdown
                    remaining = capture_delay - (current_time - motion_detected_time)
                    print(f"\r⏳ Capturing in: {remaining:.1f}s", end="", flush=True)
            elif not classification_in_progress:
                # No motion detected, reset motion detection time only if we're not in capture delay period
                if motion_detected_time != 0 and current_time - motion_detected_time < capture_delay:
                    # Still in capture delay period, don't reset - continue countdown
                    remaining = capture_delay - (current_time - motion_detected_time)
                    print(f"\r⏳ Capturing in: {remaining:.1f}s", end="", flush=True)
                else:
                    # No motion and not in capture delay period, reset
                    if motion_detected_time != 0:
                        motion_detected_time = 0
                    print(f"\r⏳ No motion detected (area: {motion_area:.0f})", end="", flush=True)
            
            # Show live feed (optional - comment out if you don't want to see the video)
            # cv2.imshow('Motion Detection', frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break
            
            time.sleep(0.033)  # ~30fps
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping motion detection...")
    finally:
        cap.release()
        cv2.destroyAllWindows()

def main():
    print("🚀 Starting Waste Wizard Motion-Based Auto-Capture")
    print("=" * 60)
    print("📋 Features:")
    print("  • Motion detection using background subtraction")
    print("  • Automatic capture when motion detected")
    print("  • Instant classification after capture")
    print("  • Runs classification model on captured images")
    print("  • 5-second cooldown between captures")
    print("=" * 60)
    print("💡 Behavior:")
    print("  • Learns background for 5 seconds on startup")
    print("  • Detects motion continuously")
    print("  • Automatically captures and classifies when motion found")
    print("  • Press Ctrl+C to stop")
    print("=" * 60)
    print("⚙️  Motion Settings:")
    print(f"  • Motion threshold: {motion_threshold} pixels")
    print(f"  • Min motion frames: {min_motion_frames}")
    print(f"  • Capture delay: {capture_delay} seconds")
    print(f"  • Capture cooldown: {capture_cooldown} seconds")
    print("=" * 60)
    
    try:
        # Start motion detection loop
        motion_detection_loop()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping motion detection...")
    except Exception as e:
        print(f"❌ Error: {e}")
    print("✅ Motion detection stopped")

if __name__ == "__main__":
    main()
