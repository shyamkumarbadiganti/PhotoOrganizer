const AWS = require('aws-sdk');
const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

// Configure AWS SDK
AWS.config.update({ region: 'us-west-2' });

const s3 = new AWS.S3();
const rekognition = new AWS.Rekognition();

const app = express();
const upload = multer({ dest: 'uploads/' });

// Function to upload image to S3
const uploadToS3 = async (bucketName, filePath, fileName) => {
  const fileContent = fs.readFileSync(filePath);

  const params = {
    Bucket: bucketName,
    Key: fileName,
    Body: fileContent,
  };

  try {
    const data = await s3.upload(params).promise();
    console.log(`File uploaded successfully. ${data.Location}`);
    return data.Location;
  } catch (err) {
    console.error(err);
    throw err;
  }
};

// Function to detect faces in an image using Rekognition
const detectFaces = async (bucketName, fileName) => {
  const params = {
    Image: {
      S3Object: {
        Bucket: bucketName,
        Name: fileName,
      },
    },
    Attributes: ['ALL'],
  };

  try {
    const data = await rekognition.detectFaces(params).promise();
    console.log('Detected faces:', JSON.stringify(data, null, 2));
    return data.FaceDetails;
  } catch (err) {
    console.error(err);
    throw err;
  }
};

// Function to index faces using Rekognition
const indexFaces = async (bucketName, fileName, collectionId) => {
  const params = {
    CollectionId: collectionId,
    Image: {
      S3Object: {
        Bucket: bucketName,
        Name: fileName,
      },
    },
  };

  try {
    const data = await rekognition.indexFaces(params).promise();
    console.log('Indexed faces:', JSON.stringify(data, null, 2));
    return data.FaceRecords;
  } catch (err) {
    console.error(err);
    throw err;
  }
};

// Function to create a collection in Rekognition
const createCollection = async (collectionId) => {
  const params = {
    CollectionId: collectionId,
  };

  try {
    const data = await rekognition.createCollection(params).promise();
    console.log('Collection created:', JSON.stringify(data, null, 2));
    return data;
  } catch (err) {
    if (err.code === 'ResourceAlreadyExistsException') {
      console.log('Collection already exists');
      return;
    }
    console.error(err);
    throw err;
  }
};

// Function to search faces by image in Rekognition
const searchFacesByImage = async (bucketName, fileName, collectionId) => {
  const params = {
    CollectionId: collectionId,
    Image: {
      S3Object: {
        Bucket: bucketName,
        Name: fileName,
      },
    },
  };

  try {
    const data = await rekognition.searchFacesByImage(params).promise();
    console.log('Searched faces:', JSON.stringify(data, null, 2));
    return data.FaceMatches;
  } catch (err) {
    console.error(err);
    throw err;
  }
};

app.use(express.static('public'));

app.post('/upload', upload.array('photos', 12), async (req, res) => {
  const bucketName = 'your-s3-bucket-name';
  const collectionId = 'my-photo-collection';
  const files = req.files;

  try {
    await createCollection(collectionId);

    const results = await Promise.all(files.map(async (file) => {
      const filePath = file.path;
      const fileName = file.originalname;
      const uniqueFileName = `${uuidv4()}_${fileName}`;

      // Upload to S3
      const s3Url = await uploadToS3(bucketName, filePath, uniqueFileName);

      // Detect faces
      const faceDetails = await detectFaces(bucketName, uniqueFileName);

      // Index faces
      const faceRecords = await indexFaces(bucketName, uniqueFileName, collectionId);

      // Search faces by image
      const faceMatches = await searchFacesByImage(bucketName, uniqueFileName, collectionId);

      // Organize photos based on face matches
      const faceIds = faceMatches.map(match => match.Face.FaceId);
      const folderName = faceIds.length ? faceIds.join('_') : 'unknown';

      // Move to folder
      const copyParams = {
        Bucket: bucketName,
        CopySource: `${bucketName}/${uniqueFileName}`,
        Key: `${folderName}/${uniqueFileName}`,
      };
      await s3.copyObject(copyParams).promise();

      // Delete original file
      const deleteParams = {
        Bucket: bucketName,
        Key: uniqueFileName,
      };
      await s3.deleteObject(deleteParams).promise();

      // Remove the file from local uploads
      fs.unlinkSync(filePath);

      return {
        s3Url,
        faceDetails,
        faceMatches,
        folderName,
      };
    }));

    res.json(results);
  } catch (err) {
    res.status(500).send('Error processing the images');
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
