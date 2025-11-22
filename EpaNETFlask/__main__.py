"""
Flask Web GUI for EPANET

This module provides a Flask-based web GUI for EPANET network analysis.
Run with: python -m EpaNETFlask
"""

from flask import Flask, render_template_string, request, jsonify, send_file
from pathlib import Path
import sys
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Add parent directory to path to import epanet_wrapper
sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_wrapper import EpanetWrapper

app = Flask(__name__)
app.epanet = EpanetWrapper()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>EPANET Flask GUI</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .upload-section { margin: 20px 0; padding: 20px; border: 1px solid #ddd; }
        .button { padding: 10px 20px; margin: 5px; cursor: pointer; }
        .status { margin: 10px 0; padding: 10px; background: #f0f0f0; }
        .plot-section { margin: 20px 0; }
        img { max-width: 100%; }
    </style>
</head>
<body>
    <div class="container">
        <h1>EPANET Network Analysis</h1>
        
        <div class="upload-section">
            <h2>Upload EPANET File</h2>
            <form id="uploadForm" enctype="multipart/form-data">
                <input type="file" name="file" accept=".inp" required>
                <button type="submit" class="button">Load File</button>
            </form>
            <div id="status" class="status">No file loaded.</div>
        </div>
        
        <div class="upload-section">
            <h2>Actions</h2>
            <button onclick="runSimulation()" class="button" id="runBtn" disabled>Run Simulation</button>
            <button onclick="displayNetwork()" class="button" id="displayBtn" disabled>Display Network</button>
        </div>
        
        <div class="plot-section" id="plotSection" style="display:none;">
            <h2>Network Visualization</h2>
            <img id="networkPlot" src="" alt="Network Plot">
        </div>
    </div>
    
    <script>
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const response = await fetch('/upload', { method: 'POST', body: formData });
            const data = await response.json();
            document.getElementById('status').textContent = data.message;
            if (data.success) {
                document.getElementById('runBtn').disabled = false;
                document.getElementById('displayBtn').disabled = false;
            }
        });
        
        async function runSimulation() {
            const response = await fetch('/run_simulation', { method: 'POST' });
            const data = await response.json();
            alert(data.message);
        }
        
        async function displayNetwork() {
            const response = await fetch('/plot_network');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            document.getElementById('networkPlot').src = url;
            document.getElementById('plotSection').style.display = 'block';
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Main page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file provided'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})
    
    if file.filename.endswith('.inp'):
        try:
            # Save temporarily
            temp_path = Path('/tmp') / file.filename
            file.save(str(temp_path))
            
            app.epanet.load_file(temp_path)
            return jsonify({'success': True, 'message': f'File loaded: {file.filename}'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error: {e}'})
    
    return jsonify({'success': False, 'message': 'Invalid file type'})


@app.route('/run_simulation', methods=['POST'])
def run_simulation():
    """Run EPANET simulation."""
    if not app.epanet.is_loaded():
        return jsonify({'success': False, 'message': 'No file loaded'})
    
    try:
        app.epanet.run_simulation()
        return jsonify({'success': True, 'message': 'Simulation completed!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {e}'})


@app.route('/plot_network')
def plot_network():
    """Generate and return network plot."""
    if not app.epanet.is_loaded():
        return jsonify({'error': 'No file loaded'}), 400
    
    try:
        fig, ax = plt.subplots(figsize=(10, 8))
        app.epanet.plot_network(ax=ax)
        
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        plt.close(fig)
        
        return send_file(img_buffer, mimetype='image/png')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def main():
    """Main entry point."""
    print("Starting EPANET Flask GUI...")
    print("Open your browser and navigate to: http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)


if __name__ == '__main__':
    main()

