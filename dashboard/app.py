from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
import os
import json
import glob
from datetime import datetime
import re
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Path to the detected images directory (relative to the dashboard folder)
DETECTED_IMAGES_PATH = "detected_images"

# Global variables for real-time updates
latest_classification = None
classification_lock = threading.Lock()

scanning_active = False 

@app.route('/toggle_scan', methods=['POST'])
def toggle_scan():
    global scanning_active
    scanning_active = not scanning_active
    status = "running" if scanning_active else "stopped"
    print(f"Scanner is now: {status}")
    return {"status": status}

def get_classification_data():
    """
    Get all classification data from the detected images directory
    """
    classifications = []
    
    # Get all image files
    image_files = glob.glob(os.path.join(DETECTED_IMAGES_PATH, "*.jpg"))
    image_files.sort(key=os.path.getmtime, reverse=True)  # Sort by newest first
    
    for image_file in image_files:
        if os.path.exists(image_file):
            # Extract metadata from filename
            filename = os.path.basename(image_file)
            
            # Parse filename: detection_YYYYMMDD_HHMMSS_N.jpg
            match = re.match(r'detection_(\d{8})_(\d{6})_(\d+)\.jpg', filename)
            if match:
                date_str, time_str, frame_num = match.groups()
                
                # Parse date and time
                try:
                    date_obj = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                    formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_date = "Unknown"
                
                # Get file size
                file_size = os.path.getsize(image_file)
                file_size_mb = round(file_size / (1024 * 1024), 2)
                
                # For now, we'll use placeholder classification data
                # In a real implementation, you'd store this data in a database or JSON file
                classification_data = {
                    'id': len(classifications) + 1,
                    'filename': filename,
                    'image_path': f"images/{filename}",
                    'date': formatted_date,
                    'frame_number': int(frame_num),
                    'file_size_mb': file_size_mb,
                    'classification': 'Unknown',  # Placeholder
                    'confidence': 0.0,  # Placeholder
                    'timestamp': date_obj.timestamp() if 'date_obj' in locals() else 0
                }
                
                classifications.append(classification_data)
    
    return classifications

def load_classification_results():
    """
    Load classification results from a JSON file if it exists
    """
    results_file = os.path.join(DETECTED_IMAGES_PATH, "classification_results.json")
    if os.path.exists(results_file):
        try:
            with open(results_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_classification_result(filename, classification, confidence):
    """
    Save classification result to JSON file
    """
    results_file = os.path.join(DETECTED_IMAGES_PATH, "classification_results.json")
    
    # Load existing results
    results = load_classification_results()
    
    # Add new result
    results[filename] = {
        'classification': classification,
        'confidence': confidence,
        'timestamp': datetime.now().isoformat()
    }
    
    # Save back to file
    try:
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        return True
    except:
        return False

@app.route('/')
def dashboard():
    """
    Main dashboard page
    """
    classifications = get_classification_data()
    results = load_classification_results()
    
    # Merge classification data with results
    for item in classifications:
        if item['filename'] in results:
            item['classification'] = results[item['filename']]['classification']
            item['confidence'] = results[item['filename']]['confidence']
    
    return render_template('dashboard.html', classifications=classifications)

@app.route('/user')
def user_interface():
    return render_template('user_interface.html')

@app.route('/api/classifications')
def api_classifications():
    """
    API endpoint to get all classifications
    """
    classifications = get_classification_data()
    results = load_classification_results()
    
    # Merge classification data with results
    for item in classifications:
        if item['filename'] in results:
            item['classification'] = results[item['filename']]['classification']
            item['confidence'] = results[item['filename']]['confidence']
    
    return jsonify(classifications)

@app.route('/api/classify', methods=['POST'])
def api_classify():
    """
    API endpoint to manually classify an image
    """
    data = request.get_json()
    filename = data.get('filename')
    classification = data.get('classification')
    confidence = data.get('confidence', 0.0)
    
    if filename and classification:
        success = save_classification_result(filename, classification, confidence)
        return jsonify({'success': success})
    
    return jsonify({'success': False, 'error': 'Missing filename or classification'})

@app.route('/images/<filename>')
def serve_image(filename):
    """
    Serve images from the detected_images directory
    """
    return send_from_directory(DETECTED_IMAGES_PATH, filename)

@app.route('/api/stats')
def api_stats():
    """
    API endpoint to get classification statistics
    """
    classifications = get_classification_data()
    results = load_classification_results()
    
    # Count classifications
    class_counts = {}
    total_classified = 0
    total_images = len(classifications)
    
    for item in classifications:
        if item['filename'] in results:
            classification = results[item['filename']]['classification']
            class_counts[classification] = class_counts.get(classification, 0) + 1
            total_classified += 1
    
    # Calculate average confidence
    confidences = [results[item['filename']]['confidence'] 
                  for item in classifications 
                  if item['filename'] in results and 'confidence' in results[item['filename']]]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    
    stats = {
        'total_images': total_images,
        'total_classified': total_classified,
        'classification_counts': class_counts,
        'average_confidence': round(avg_confidence, 2),
        'unclassified': total_images - total_classified
    }
    
    return jsonify(stats)

@app.route('/api/latest_classification')
def api_latest_classification():
    """
    API endpoint to get the latest classification for user interface
    Only returns data if detection system is actively running
    """
    try:
        # Check if detection system is actively running by checking file modification time
        results_file = os.path.join(DETECTED_IMAGES_PATH, 'classification_results.json')
        
        if not os.path.exists(results_file):
            return jsonify({'classification': None, 'confidence': 0, 'detection_active': False})
        
        # Check if file was modified recently (within last 60 seconds)
        file_mtime = os.path.getmtime(results_file)
        current_time = time.time()
        
        if current_time - file_mtime > 60:  # More than 60 seconds old
            return jsonify({'classification': None, 'confidence': 0, 'detection_active': False})
        
        results = load_classification_results()
        
        if not results:
            return jsonify({'classification': None, 'confidence': 0, 'detection_active': False})

        # Get the most recent classification
        latest_file = max(results.keys(), key=lambda x: results[x]['timestamp'])
        latest_result = results[latest_file]
        
        # Check if the latest result is recent (within last 60 seconds)
        latest_timestamp = datetime.fromisoformat(latest_result['timestamp'].replace('Z', '+00:00'))
        latest_time = latest_timestamp.timestamp()
        
        if current_time - latest_time > 60:  # More than 60 seconds old
            return jsonify({'classification': None, 'confidence': 0, 'detection_active': False})

        result_data = {
            'classification': latest_result['classification'],
            'confidence': latest_result['confidence'],
            'timestamp': latest_result['timestamp'],
            'detection_active': True
        }
        
        # Debug: Log the data being sent to frontend
        print(f"📡 Sending to frontend: {result_data}")
        
        return jsonify(result_data)
        
    except Exception as e:
        print(f"Error in latest_classification: {e}")
        return jsonify({'classification': None, 'confidence': 0, 'detection_active': False})

@app.route('/api/delete_classification', methods=['POST'])
def api_delete_classification():
    """
    API endpoint to delete a classification and its associated image
    """
    try:
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'success': False, 'error': 'No filename provided'}), 400
        
        # Paths for the image and JSON files
        image_path = os.path.join(DETECTED_IMAGES_PATH, filename)
        json_path = os.path.join(DETECTED_IMAGES_PATH, 'classification_results.json')
        
        # Delete the image file
        if os.path.exists(image_path):
            os.remove(image_path)
        
        # Update the JSON file to remove the classification
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                results = json.load(f)
            
            # Remove the classification from the results
            if filename in results:
                del results[filename]
                
                # Write back the updated results
                with open(json_path, 'w') as f:
                    json.dump(results, f, indent=2)
        
        return jsonify({'success': True, 'message': 'Classification deleted successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/classify_image', methods=['POST'])
def api_classify_image():
    """
    API endpoint to classify an image using Roboflow workflow
    """
    try:
        from inference_sdk import InferenceHTTPClient
        
        # Check if image was uploaded
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image provided'}), 400
        
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'success': False, 'error': 'No image selected'}), 400
        
        # Initialize Roboflow client
        client = InferenceHTTPClient(
            api_url="https://serverless.roboflow.com",
            api_key="Mqg6MjfPG888hkIAilqR"
        )
        
        # Run workflow classification
        result = client.run_workflow(
            workspace_name="smartsort-vfpxc",
            workflow_id="smartsort-classify-v1",
            images={
                "image": image_file
            },
            use_cache=True
        )
        
        # Parse the result
        if result and isinstance(result, list) and len(result) > 0:
            model_predictions = result[0].get('model_predictions', {})
            predictions = model_predictions.get('predictions', [])
            
            if predictions:
                first_prediction = predictions[0]
                classification = first_prediction.get('class', 'Unknown')
                confidence = first_prediction.get('confidence', 0)
                confidence_pct = confidence * 100 if isinstance(confidence, (int, float)) else confidence
                
                return jsonify({
                    'success': True,
                    'classification': classification,
                    'confidence': round(confidence_pct, 2)
                })
            else:
                return jsonify({
                    'success': True,
                    'classification': 'Unknown',
                    'confidence': 0
                })
        else:
            return jsonify({
                'success': True,
                'classification': 'Unknown',
                'confidence': 0
            })
            
    except Exception as e:
        print(f"Classification error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/realtime_update', methods=['POST'])
def api_realtime_update():
    """
    API endpoint to receive real-time updates from integrated_auto_capture.py
    """
    try:
        data = request.get_json()
        
        # Update the latest classification
        update_latest_classification(data)
        
        # Also save to classification results file for polling-based frontend
        filename = data.get('filename')
        classification = data.get('classification')
        confidence = data.get('confidence')
        
        if filename and classification:
            save_classification_result(filename, classification, confidence)
        
        print(f"📡 Real-time update received: {classification} ({confidence}%)")
        
        return jsonify({'success': True, 'message': 'Real-time update received'})
        
    except Exception as e:
        print(f"Real-time update error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/detection_status')
def api_detection_status():
    """
    API endpoint to check if the detection system is running
    """
    try:
        # Check if integrated_auto_capture.py is running by looking for recent activity
        results_file = os.path.join(DETECTED_IMAGES_PATH, 'classification_results.json')
        
        if os.path.exists(results_file):
            # Check if file was modified recently (within last 30 seconds)
            file_mtime = os.path.getmtime(results_file)
            current_time = time.time()
            
            if current_time - file_mtime < 30:
                return jsonify({'running': True, 'message': 'Detection system is active'})
        
        return jsonify({'running': False, 'message': 'Detection system is not running'})
        
    except Exception as e:
        return jsonify({'running': False, 'error': str(e)})

@app.route('/api/system_status')
def api_system_status():
    """
    API endpoint to check overall system status
    """
    try:
        # Check if system status file exists and is recent
        status_file = os.path.join(DETECTED_IMAGES_PATH, 'system_status.json')
        system_ready = False
        
        if os.path.exists(status_file):
            # Check if file was modified recently (within last 10 minutes)
            file_mtime = os.path.getmtime(status_file)
            current_time = time.time()
            
            if current_time - file_mtime < 600:  # 10 minutes (more generous)
                try:
                    with open(status_file, 'r') as f:
                        status_data = json.load(f)
                        system_ready = status_data.get('system_ready', False)
                except:
                    system_ready = False
        
        # Check if detection system is actively running
        results_file = os.path.join(DETECTED_IMAGES_PATH, 'classification_results.json')
        detection_active = False
        
        if os.path.exists(results_file):
            # Check if file was modified recently (within last 60 seconds)
            file_mtime = os.path.getmtime(results_file)
            current_time = time.time()
            
            if current_time - file_mtime < 60:
                detection_active = True
        
        # System is ready if either:
        # 1. System status file indicates ready AND detection is active, OR
        # 2. Detection is active (meaning system is running)
        overall_ready = (system_ready and detection_active) or detection_active
        
        return jsonify({
            'detection_active': detection_active,
            'system_ready': overall_ready,
            'message': 'System ready' if overall_ready else 'System not ready'
        })
        
    except Exception as e:
        return jsonify({
            'detection_active': False,
            'system_ready': False,
            'error': str(e)
        })

@app.route('/api/refresh_frontend', methods=['POST'])
def api_refresh_frontend():
    """
    API endpoint to trigger frontend refresh
    """
    try:
        # Emit refresh signal to all connected clients
        socketio.emit('refresh_page', {'message': 'System ready - refreshing page'})
        print("🔄 Frontend refresh signal sent to all clients")
        print(f"📊 Connected clients: {len(socketio.server.manager.rooms)}")
        return jsonify({'success': True, 'message': 'Frontend refresh signal sent'})
        
    except Exception as e:
        print(f"Frontend refresh error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/manual_override', methods=['POST'])
def api_manual_override():
    """
    API endpoint to handle manual classification overrides
    """
    try:
        data = request.get_json()
        classification = data.get('classification')
        confidence = data.get('confidence', 100.0)
        timestamp = data.get('timestamp')
        
        if not classification:
            return jsonify({'success': False, 'error': 'No classification provided'}), 400
        
        # Load existing results
        results_file = os.path.join(DETECTED_IMAGES_PATH, 'classification_results.json')
        results = {}
        
        if os.path.exists(results_file):
            try:
                with open(results_file, 'r') as f:
                    results = json.load(f)
            except:
                results = {}
        
        # Find the most recent classification to update
        if results:
            # Get the most recent entry
            latest_file = max(results.keys(), key=lambda x: results[x]['timestamp'])
            
            # Update the classification
            results[latest_file]['classification'] = classification
            results[latest_file]['confidence'] = confidence
            results[latest_file]['timestamp'] = timestamp or datetime.now().isoformat()
            results[latest_file]['manual_override'] = True
            
            # Save updated results
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            print(f"✅ Manual override saved: {classification} ({confidence}%)")
            
            return jsonify({
                'success': True, 
                'message': f'Classification updated to {classification}',
                'updated_file': latest_file
            })
        else:
            return jsonify({'success': False, 'error': 'No classifications found to override'}), 404
            
    except Exception as e:
        print(f"Manual override error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'message': 'Connected to BinWaste system'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('request_latest_classification')
def handle_latest_classification():
    with classification_lock:
        if latest_classification:
            emit('new_classification', latest_classification)

def update_latest_classification(classification_data):
    """Update the latest classification and notify clients"""
    global latest_classification
    with classification_lock:
        latest_classification = classification_data
        socketio.emit('new_classification', classification_data)

if __name__ == '__main__':
    # Create detected_images directory if it doesn't exist
    os.makedirs(DETECTED_IMAGES_PATH, exist_ok=True)
    
    print("🚀 Starting BinWaste Dashboard")
    print("=" * 50)
    print("📊 Dashboard Features:")
    print("  • View all captured images")
    print("  • See classification results")
    print("  • Manual classification interface")
    print("  • Statistics and analytics")
    print("=" * 50)
    print("🌐 Access the dashboard at: http://localhost:5001")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5001)
