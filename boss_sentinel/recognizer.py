import os
import numpy as np
import torch
from PIL import Image
from facenet_pytorch import InceptionResnetV1
from typing import Dict, Optional, Tuple

class FaceRecognizer:
    """基于FaceNet的人脸识别器"""
    
    def __init__(self, known_faces_dir: str = "known_faces"):
        """
        初始化人脸识别器
        
        参数:
            known_faces_dir: 已知人脸图像存储目录
        """
        self.known_faces_dir = known_faces_dir
        self.resnet = InceptionResnetV1(pretrained='vggface2').eval()
        self.known_embeddings = self._load_known_faces()
        
    def _load_known_faces(self) -> Dict[str, np.ndarray]:
        """加载已知人脸特征向量"""
        known_embeddings = {}
        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir, exist_ok=True)
            return known_embeddings
            
        for filename in os.listdir(self.known_faces_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                try:
                    img_path = os.path.join(self.known_faces_dir, filename)
                    img = Image.open(img_path).resize((160, 160))
                    img_tensor = torch.tensor(np.array(img)).permute(2, 0, 1).float().unsqueeze(0)
                    embedding = self.resnet(img_tensor).detach().numpy()
                    known_embeddings[filename.split('.')[0]] = embedding
                except Exception as e:
                    print(f"加载图像 {filename} 失败: {e}")
                    
        return known_embeddings
        
    def get_embedding(self, face_img: np.ndarray) -> np.ndarray:
        """
        获取人脸图像的特征向量
        
        参数:
            face_img: 人脸图像(BGR格式)
            
        返回:
            人脸特征向量
        """
        face_pil = Image.fromarray(cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)).resize((160, 160))
        face_tensor = torch.tensor(np.array(face_pil)).permute(2, 0, 1).float().unsqueeze(0)
        return self.resnet(face_tensor).detach().numpy()
        
    def compare_faces(self, embedding: np.ndarray, threshold: float = 0.7) -> Tuple[Optional[str], float]:
        """
        与已知人脸比对
        
        参数:
            embedding: 待比对人脸特征向量
            threshold: 相似度阈值
            
        返回:
            (匹配的人名, 最高相似度)
        """
        best_match = None
        best_similarity = 0.0
        
        for name, known_embedding in self.known_embeddings.items():
            similarity = np.dot(embedding, known_embedding.T) / (
                np.linalg.norm(embedding) * np.linalg.norm(known_embedding))
                
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = name if similarity > threshold else None
                
        return best_match, best_similarity