from ultralytics import YOLO #Imports the YOLO class from the Ultralytics library.

model = YOLO("yolov8n.pt") #Loads the YOLOv8n model.

# Run the model on the image
results = model("sample_data/images/fire.jpg")

# Print the raw results
print(results)