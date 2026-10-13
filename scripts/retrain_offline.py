#!/usr/bin/env python3
"""
scripts/retrain_offline.py

Fully reproducible offline retraining pipeline for the 9-feature DDQN controller.
Documents exact hyperparameter provenance, random seeds, and transition replay generation.
"""

import os
import sys
import random
import numpy as np
import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.losses import Huber

# Pin reproducibility seeds
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

# Physical bounds for 9 features: [q1, dt1, q2, dt2, q3, dt3, buffer, fps, bitrate]
FEATURE_SCALES = np.array([
    64.0,     # q1 (pkts)
    50000.0,  # dt1 (us)
    64.0,     # q2 (pkts)
    50000.0,  # dt2 (us)
    64.0,     # q3 (pkts)
    50000.0,  # dt3 (us)
    60.0,     # buffer (s)
    30.0,     # fps
    2000.0    # bitrate (kbps)
], dtype=np.float32)

def scale_state(state):
    return np.clip(np.asarray(state, dtype=np.float32) / FEATURE_SCALES, 0.0, 1.0)

def compute_balanced_reward(state, action):
    # state: [q1, dt1, q2, dt2, q3, dt3, buffer, fps, bitrate]
    q_max = max(state[0], state[2], state[4])
    buf = state[6]
    fps = state[7]
    
    r_fps = fps / 30.0
    r_buf = min(1.0, buf / 25.0) * 0.8
    r_stall = 3.0 if fps == 0.0 else 0.0
    r_queue = max(0.0, (q_max - 15.0) / 20.0) * 0.5
    
    return r_fps + r_buf - r_stall - r_queue

def build_q_network():
    model = Sequential([
        Dense(32, activation='relu', input_shape=(9,), name='dense'),
        Dense(32, activation='relu', name='dense_1'),
        Dense(3, activation='linear', name='dense_2')
    ])
    model.compile(optimizer=Adam(learning_rate=1e-3), loss=Huber())
    return model

def generate_synthetic_experience(n_transitions=10000):
    experience = []
    for _ in range(n_transitions):
        # Sample realistic network conditions reflecting testbed distributions
        # Low queue occupancy (mostly 0-3 pkts), variable delay, varying buffer/FPS
        q1 = np.random.choice([0, 1, 2, 3], p=[0.85, 0.10, 0.03, 0.02])
        dt1 = np.random.uniform(500, 20000)
        q2 = np.random.choice([0, 1, 2, 3], p=[0.80, 0.12, 0.05, 0.03])
        dt2 = np.random.uniform(500, 35000)
        q3 = np.random.choice([0, 1, 2, 5, 10], p=[0.75, 0.15, 0.05, 0.03, 0.02])
        dt3 = np.random.uniform(500, 45000)
        buf = np.random.uniform(5.0, 60.0)
        fps = 30.0 if buf > 10.0 else (24.0 if buf > 3.0 else 0.0)
        br = 1040.0 if fps == 30.0 else (490.0 if fps == 24.0 else 140.0)
        
        s = np.array([q1, dt1, q2, dt2, q3, dt3, buf, fps, br], dtype=np.float32)
        action = np.random.choice(3) # 0: Inc, 1: Dec, 2: Hold
        
        # Next state dynamics
        if action == 0: # Increase target delay -> queue drains slower, buffer may grow
            buf_next = min(60.0, buf + np.random.uniform(0.5, 1.5))
            dt2_next = min(50000.0, dt2 + 5000.0)
        elif action == 1: # Decrease target delay -> queue drops, buffer might drain if packets dropped
            buf_next = max(0.0, buf - np.random.uniform(0.5, 2.0))
            dt2_next = max(500.0, dt2 - 5000.0)
        else: # Hold
            buf_next = max(0.0, min(60.0, buf + np.random.uniform(-0.5, 0.5)))
            dt2_next = dt2
            
        fps_next = 30.0 if buf_next > 10.0 else (24.0 if buf_next > 3.0 else 0.0)
        br_next = 1040.0 if fps_next == 30.0 else (490.0 if fps_next == 24.0 else 140.0)
        s_prime = np.array([q1, dt1, q2, dt2_next, q3, dt3, buf_next, fps_next, br_next], dtype=np.float32)
        
        reward = compute_balanced_reward(s_prime, action)
        experience.append((scale_state(s), action, reward, scale_state(s_prime)))
        
    return experience

def main():
    print(f"[*] Initializing offline retraining with SEED={SEED}...")
    q_net = build_q_network()
    target_net = build_q_network()
    target_net.set_weights(q_net.get_weights())
    
    print("[*] Generating synthetic experience replay buffer...")
    replay = generate_synthetic_experience(n_transitions=10000)
    
    gamma = 0.99
    batch_size = 32
    episodes = 250
    steps_per_episode = 40
    
    print(f"[*] Training DDQN for {episodes} episodes...")
    for ep in range(episodes):
        losses = []
        for _ in range(steps_per_episode):
            batch = random.sample(replay, batch_size)
            states = np.array([b[0] for b in batch])
            actions = np.array([b[1] for b in batch])
            rewards = np.array([b[2] for b in batch])
            next_states = np.array([b[3] for b in batch])
            
            # DDQN target
            next_q_online = q_net.predict_on_batch(next_states)
            best_actions = np.argmax(next_q_online, axis=1)
            next_q_target = target_net.predict_on_batch(next_states)
            targets = rewards + gamma * next_q_target[np.arange(batch_size), best_actions]
            
            current_q = q_net.predict_on_batch(states)
            current_q[np.arange(batch_size), actions] = targets
            
            loss = q_net.train_on_batch(states, current_q)
            losses.append(loss)
            
        if (ep + 1) % 50 == 0:
            target_net.set_weights(q_net.get_weights())
            mean_loss = np.mean(losses)
            print(f"  Episode {ep+1:3d}/{episodes} | Mean Huber Loss: {mean_loss:.4f}")
            
    out_dir = "local_controller/agent_models_fixed"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "online_network_retrained_balanced.h5")
    q_net.save(out_path)
    print(f"[+] Retrained model successfully saved to {out_path}")

if __name__ == "__main__":
    main()
