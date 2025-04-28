import numpy as np
import mediapipe as mp 
import math


def normalized_to_pixel(normalized_x, normalized_y, image_width, image_height):
    x_px = min(int(normalized_x * image_width), image_width - 1)
    y_px = min(int(normalized_y * image_height), image_height - 1)
    return x_px, y_px

def eye_aspect_ratio(eye):
    dist_p2_p6 = math.dist(eye[1],eye[5])
    dist_p3_p5 = math.dist(eye[2],eye[4])
    dist_p1_p4 = math.dist(eye[0],eye[3])
    
    return (dist_p2_p6 + dist_p3_p5) / (2.0 * dist_p1_p4) 

def get_ear(landmarks, refer_idxs, frame_w, frame_h):
    try:
        coords_pts = []
        for i in refer_idxs:
            lm = landmarks[i]
            coord = normalized_to_pixel(lm.x,lm.y,frame_w,frame_h)
            
            coords_pts.append(coord)
        
        ear = eye_aspect_ratio(coords_pts)
    except:
        ear = 0.0
        coords_pts = None
    
    return ear, coords_pts

def calculate_avg_ear(lms, left_eye_idxs, right_eye_idxs, image_w, image_h):
    left_ear, left_lm_coords = get_ear(lms,left_eye_idxs,image_w,image_h)
    right_ear, right_lm_coords = get_ear(lms,right_eye_idxs,image_w,image_h)
    
    avg_ear = (left_ear + right_ear) / 2.0
    
    return avg_ear, (left_lm_coords, right_lm_coords)
        
def get_media_pipe(max_num_faces=1,refine_landmarks=True,min_detection_confidence=0.5,min_tracking_confidence=0.5):
    return mp.solutions.face_mesh.FaceMesh(
        max_num_faces = max_num_faces,
        refine_landmarks=refine_landmarks,
        min_detection_confidence = min_detection_confidence,
        min_tracking_confidence = min_tracking_confidence
    )
        
