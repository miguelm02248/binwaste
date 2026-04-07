import time
import os
import threading
import sys
from datetime import datetime
from picamera import PiCamera
from inference import InferencePipeline
from inference.core.interfaces.stream.sinks import render_boxes
from inference_sdk import InferenceHTTPClient

# Global variables for timing control
last_detection_time = 0
detection_interval = 5.0  # seconds between detections
frame_count = 0
manual_capture_requested = False

def keyboard_input_handler():
    """
    Handle keyboard input in a separate thread
    """
    global manual_capture_requested
    while True:
        try:
            user_input = input()
            if user_input.lower() in ['c', 'capture', 'p', 'photo']:
                manual_capture_requested = True
                print("📸 Manual capture requested!")
        except EOFError:
            break

def capture_and_analyze():
    """
    Capture image with PiCamera, then run classification inference
    """
    global frame_count
    
    frame_count += 1
    
    # Create images directory if it doesn't exist
    if not os.path.exists('detected_images'):
        os.makedirs('detected_images')
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"detected_images/detection_{timestamp}_{frame_count}.jpg"
    
    try:
        print(f"\n📸 Capturing image with PiCamera...")
        
        # Initialize PiCamera and capture image
        with PiCamera() as camera:
            camera.resolution = (1280, 720)  # Higher resolution for better analysis
            camera.start_preview()
            time.sleep(1)  # Give camera time to adjust
            camera.capture(filename)
            camera.stop_preview()
        
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
            workflow_id="smartsort-classify-v1",
            #alternative models
                #workflow_id="smartsort-classify-simple-v2",
                #workflow_id="smartsort-classify-simple-v3",
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
        
        return True
        
    except Exception as e:
        print(f"❌ Error capturing/analyzing image: {e}")
        return False

def custom_detection_sink(result, video_frame):
    """
    Custom sink that only handles manual capture requests
    """
    global manual_capture_requested
    
    # Check for manual capture request
    if manual_capture_requested:
        print(f"\n📸 Manual capture triggered!")
        manual_capture_requested = False
        success = capture_and_analyze()
        if success:
            print(f"✅ Manual capture and analysis completed!")
        else:
            print("❌ Manual capture failed!")
        print("=" * 50)
        return

def main():
    print("🚀 Starting Waste Wizard PiCamera Classification")
    print("=" * 60)
    print("📋 Features:")
    print("  • PiCamera integration")
    print("  • Manual capture with 'c', 'capture', 'p', or 'photo'")
    print("  • Instant classification after capture")
    print("  • Runs classification model on captured images")
    print("=" * 60)
    print("💡 Commands:")
    print("  • Type 'c', 'capture', 'p', or 'photo' + Enter to capture and analyze")
    print("  • Press Ctrl+C to stop")
    print("=" * 60)
    
    # Start keyboard input handler in a separate thread
    keyboard_thread = threading.Thread(target=keyboard_input_handler, daemon=True)
    keyboard_thread.start()
    
    try:
        print("🔄 Initializing detection pipeline...")
        
        # Initialize the inference pipeline for live detection
        pipeline = InferencePipeline.init(
            model_id="trash-sort-objd/1",
            video_reference=0,
            api_key="Mqg6MjfPG888hkIAilqR",
            on_prediction=custom_detection_sink
        )
        
        print("✅ Pipeline initialized successfully!")
        print("🎥 Starting live detection...")
        print("💡 Press Ctrl+C to stop")
        print()
        
        # Start the pipeline
        pipeline.start()
        pipeline.join()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping detection...")
    except Exception as e:
        print(f"❌ Error: {e}")
    print("✅ Detection stopped")

if __name__ == "__main__":
    main()
