import cv2
import numpy as np
import os
from matplotlib import pyplot as plt
import time
import mediapipe as mp
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from flask_socketio import SocketIO, emit


class VideoCamera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(0)

    def pause(self):
        self.video.release()

    def get_frame(self):
        ret, frame = self.video.read()
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()

    def translate(self):
        mp_holistic = mp.solutions.holistic  # Holistic model
        mp_drawing = mp.solutions.drawing_utils  # Drawing utilities

        def mediapipe_detection(image, model):
            # COLOR CONVERSION BGR 2 RGB
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False                  # Image is no longer writeable
            results = model.process(image)                 # Make prediction
            image.flags.writeable = True                   # Image is now writeable
            # COLOR COVERSION RGB 2 BGR
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            return image, results

        def draw_styled_landmarks(image, results):
            # Draw face connections
            mp_drawing.draw_landmarks(image, results.face_landmarks, mp_holistic.FACEMESH_TESSELATION,
                                      mp_drawing.DrawingSpec(
                                          color=(80, 110, 10), thickness=1, circle_radius=1),
                                      mp_drawing.DrawingSpec(
                                          color=(80, 256, 121), thickness=1, circle_radius=1)
                                      )
            # Draw pose connections
            mp_drawing.draw_landmarks(image, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS,
                                      mp_drawing.DrawingSpec(
                                          color=(80, 22, 10), thickness=2, circle_radius=4),
                                      mp_drawing.DrawingSpec(
                                          color=(80, 44, 121), thickness=2, circle_radius=2)
                                      )
            # Draw left hand connections
            mp_drawing.draw_landmarks(image, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS,
                                      mp_drawing.DrawingSpec(
                                          color=(121, 22, 76), thickness=2, circle_radius=4),
                                      mp_drawing.DrawingSpec(
                                          color=(121, 44, 250), thickness=2, circle_radius=2)
                                      )
            # Draw right hand connections
            mp_drawing.draw_landmarks(image, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS,
                                      mp_drawing.DrawingSpec(
                                          color=(245, 117, 66), thickness=2, circle_radius=4),
                                      mp_drawing.DrawingSpec(
                                          color=(245, 66, 230), thickness=2, circle_radius=2)
                                      )

        # pose = np.array([[res.x, res.y, res.z, res.visibility] for res in results.pose_landmarks.landmark]).flatten(
        # ) if results.pose_landmarks else np.zeros(132)
        # face = np.array([[res.x, res.y, res.z] for res in results.face_landmarks.landmark]).flatten(
        # ) if results.face_landmarks else np.zeros(1404)
        # lh = np.array([[res.x, res.y, res.z] for res in results.left_hand_landmarks.landmark]).flatten(
        # ) if results.left_hand_landmarks else np.zeros(21*3)
        # rh = np.array([[res.x, res.y, res.z] for res in results.right_hand_landmarks.landmark]).flatten(
        # ) if results.right_hand_landmarks else np.zeros(21*3)
        # face = np.array([[res.x, res.y, res.z] for res in results.face_landmarks.landmark]).flatten(
        # ) if results.face_landmarks else np.zeros(1404)

        def extract_keypoints(results):
            pose = np.array([[res.x, res.y, res.z, res.visibility] for res in results.pose_landmarks.landmark]).flatten(
            ) if results.pose_landmarks else np.zeros(33*4)
            face = np.array([[res.x, res.y, res.z] for res in results.face_landmarks.landmark]).flatten(
            ) if results.face_landmarks else np.zeros(468*3)
            lh = np.array([[res.x, res.y, res.z] for res in results.left_hand_landmarks.landmark]).flatten(
            ) if results.left_hand_landmarks else np.zeros(21*3)
            rh = np.array([[res.x, res.y, res.z] for res in results.right_hand_landmarks.landmark]).flatten(
            ) if results.right_hand_landmarks else np.zeros(21*3)
            return np.concatenate([pose, face, lh, rh])

        # Path for exported data, numpy arrays
        DATA_PATH = os.path.join('MP_Data')

        # Actions that we try to detect
        actions = np.array(['hola', 'gracias', 'denada'])

        # Thirty videos worth of data
        no_sequences = 30

        # Videos are going to be 30 frames in length
        sequence_length = 30

        label_map = {label: num for num, label in enumerate(actions)}

        sequences, labels = [], []
        for action in actions:
            for sequence in range(no_sequences):
                window = []
                for frame_num in range(sequence_length):
                    res = np.load(os.path.join(DATA_PATH, action, str(
                        sequence), "{}.npy".format(frame_num)))
                    window.append(res)
                sequences.append(window)
                labels.append(label_map[action])

        model = Sequential()
        model.add(LSTM(64, return_sequences=True,
                  activation='relu', input_shape=(30, 1662)))
        model.add(LSTM(128, return_sequences=True, activation='relu'))
        model.add(LSTM(64, return_sequences=False, activation='relu'))
        model.add(Dense(64, activation='relu'))
        model.add(Dense(32, activation='relu'))
        model.add(Dense(actions.shape[0], activation='softmax'))

        model.load_weights('./action.h5')

        sequence = []
        sentence = []
        threshold = 0.8

        cap = self.video
        # Set mediapipe model
        with mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5) as holistic:
            while cap.isOpened():

                # Read feed
                ret, frame = cap.read()

                # Make detections
                image, results = mediapipe_detection(frame, holistic)

                keypoints = extract_keypoints(results)
                sequence.append(keypoints)
                sequence = sequence[-30:]

                if len(sequence) == 30:
                    res = model.predict(np.expand_dims(sequence, axis=0))[0]
                    toEmit = actions[np.argmax(res)]
                    emit("data", {'data': str(toEmit)}, broadcast=True)
