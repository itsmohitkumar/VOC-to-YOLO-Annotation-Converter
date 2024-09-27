import os
import xml.etree.ElementTree as ET

# Convert VOC bounding box format to YOLO format
def convert_box(image_size, box):
    image_w, image_h = image_size
    box_xmin, box_xmax, box_ymin, box_ymax = box
    
    # Center x, y coordinates
    x_center = (box_xmin + box_xmax) / 2.0
    y_center = (box_ymin + box_ymax) / 2.0
    
    # Width and height of the box
    box_width = box_xmax - box_xmin
    box_height = box_ymax - box_ymin
    
    # Normalize coordinates
    x_center /= image_w
    y_center /= image_h
    box_width /= image_w
    box_height /= image_h
    
    return x_center, y_center, box_width, box_height

# Convert annotations from VOC XML format to YOLO format
def convert_voc_to_yolo(label_dir='./data/labels', output_dir='./data/labels'):
    # List of class names (can be passed as a parameter for flexibility)
    class_names = ['trafficlight', 'speedlimit', 'crosswalk', 'stop']

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    for annotation_file in os.listdir(label_dir):
        file_base, file_ext = os.path.splitext(annotation_file)
        
        if file_ext != '.xml':
            continue  # Skip non-XML files
        
        input_file_path = os.path.join(label_dir, annotation_file)
        output_file_path = os.path.join(output_dir, f'{file_base}.txt')
        
        try:
            tree = ET.parse(input_file_path)
            root = tree.getroot()

            # Extract image size
            size_element = root.find('size')
            image_w = int(size_element.find('width').text)
            image_h = int(size_element.find('height').text)
            
            with open(output_file_path, 'w') as output_file:
                for obj in root.iter('object'):
                    class_name = obj.find('name').text
                    
                    # Skip if the class name isn't in the predefined list
                    if class_name not in class_names:
                        continue
                    
                    # Skip difficult objects
                    difficult = obj.find('difficult')
                    if difficult is not None and int(difficult.text) == 1:
                        continue
                    
                    # Get bounding box details
                    xml_box = obj.find('bndbox')
                    bounding_box = [
                        float(xml_box.find(tag).text) for tag in ('xmin', 'xmax', 'ymin', 'ymax')
                    ]
                    
                    # Convert bounding box to YOLO format
                    yolo_box = convert_box((image_w, image_h), bounding_box)
                    class_id = class_names.index(class_name)
                    
                    # Write the YOLO format annotation to file
                    output_file.write(f"{class_id} " + " ".join(f"{val:.6f}" for val in yolo_box) + '\n')
        
        except ET.ParseError:
            print(f"Error parsing XML file: {input_file_path}")
        except Exception as e:
            print(f"Error processing file {input_file_path}: {e}")
