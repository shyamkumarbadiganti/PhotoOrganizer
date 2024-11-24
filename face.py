      
import os
from flask import Flask, request, jsonify, render_template
import boto3
import logging
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')

def compare_faces(source_image_path, target_image_path):
    with open(source_image_path, 'rb') as source_image_file:
        source_bytes = source_image_file.read()
    
    with open(target_image_path, 'rb') as target_image_file:
        target_bytes = target_image_file.read()
    
    response = rekognition.compare_faces(
        SourceImage={'Bytes': source_bytes},
        TargetImage={'Bytes': target_bytes}
    )
    
    if response['FaceMatches']:
        similarity = response['FaceMatches'][0]['Similarity']
        return similarity > 90  # Adjust the threshold as needed
    return False

def upload_to_s3(bucket_name, folder, file_path):
    s3.upload_file(file_path, bucket_name, f"{folder}/{os.path.basename(file_path)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'photo' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['photo']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        base_image_dir = 'base_images'
        base_images = {
            'A': os.path.join(base_image_dir, 'A.jpeg'),
            'B': os.path.join(base_image_dir, 'B.png'),
            'C': os.path.join(base_image_dir, 'C.jpeg')
        }
        
        tmp_dir = '/tmp'
        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)
        
        input_image_path = os.path.join(tmp_dir, secure_filename(file.filename))
        try:
            file.save(input_image_path)
            logger.info(f"File saved to {input_image_path}")
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            return jsonify({'error': 'File saving error'}), 500
        
        for folder, base_image_path in base_images.items():
            if not os.path.exists(base_image_path):
                continue  # Skip to the next base image

            try:
                if compare_faces(input_image_path, base_image_path):
                    upload_to_s3('mainbuckets123', folder, input_image_path)
                    return jsonify({'message': f'The image matches with {base_image_path}, uploaded to folder {folder}'})
            except Exception as e:
                logger.error(f"Error comparing faces or uploading to S3: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Create a new folder if no match found
        new_folder = 'new_face'
        s3.put_object(Bucket='mainbuckets123', Key=f"{new_folder}/")
        upload_to_s3('mainbuckets123', new_folder, input_image_path)
        return jsonify({'message': f'No match found, uploaded to new folder {new_folder}'})
    
    return jsonify({'error': 'File processing error'}), 500

@app.route('/folders')
def folders():
    bucket_name = 'mainbuckets123'
    
    # Fetch the list of folders
    result = []
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Delimiter='/')
        if 'CommonPrefixes' in response:
            folders = response['CommonPrefixes']
            for folder in folders:
                folder_name = folder['Prefix']
                response = s3.list_objects_v2(Bucket=bucket_name, Prefix=folder_name, Delimiter='/')
                images = [content['Key'] for content in response.get('Contents', []) if not content['Key'].endswith('/')]
                result.append({
                    'folder': folder_name.strip('/'),
                    'images': images
                })
        else:
            return jsonify([])  # No folders found
    except Exception as e:
        logger.error(f"Error fetching folders: {e}")
        return jsonify({'error': 'Error fetching folders'}), 500
    
    return jsonify(result)

@app.route('/delete_image', methods=['POST'])
def delete_image():
    data = request.json
    bucket_name = 'mainbuckets123'
    image_key = data.get('image_key')
    if not image_key:
        return jsonify({'error': 'Image key is required'}), 400
    
    try:
        s3.delete_object(Bucket=bucket_name, Key=image_key)
        return jsonify({'message': 'Image deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting image: {e}")
        return jsonify({'error': 'Error deleting image'}), 500

@app.route('/rename_folder', methods=['POST'])
def rename_folder():
    data = request.json
    bucket_name = 'mainbuckets123'
    old_folder_name = data.get('old_folder_name')
    new_folder_name = data.get('new_folder_name')
    
    if not old_folder_name or not new_folder_name:
        return jsonify({'error': 'Both old and new folder names are required'}), 400
    
    try:
        # List all objects in the old folder
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=f"{old_folder_name}/")
        for obj in response.get('Contents', []):
            old_key = obj['Key']
            new_key = old_key.replace(old_folder_name, new_folder_name, 1)
            # Copy the object to the new folder
            s3.copy_object(Bucket=bucket_name, CopySource={'Bucket': bucket_name, 'Key': old_key}, Key=new_key)
            # Delete the old object
            s3.delete_object(Bucket=bucket_name, Key=old_key)
        
        return jsonify({'message': 'Folder renamed successfully'})
    except Exception as e:
        logger.error(f"Error renaming folder: {e}")
        return jsonify({'error': 'Error renaming folder'}), 500

if __name__ == '__main__':
    app.run(debug=True)

