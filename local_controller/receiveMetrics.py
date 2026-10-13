import tail 
import threading
import pandas as pd
import numpy as np
from collections import deque
import datetime
from agent import DDQN
from environment import ControlPlaneEnvironment
import os
import subprocess
import csv
from io import StringIO
import argparse
import time 

#const
INT_TYPE = 0
DASH_TYPE = 1
FIRST_SECOND = 0
FOURTH_SECOND = -1
DEFAULT_QUEUE_SIZE = 64
DEFAULT_TARGET_DELAY = 50000
join_lock = threading.Lock()


def sendtoRl(sample):
    global ddqn
    global env
    global experiment_id

    
    df_INT = sample.iloc[:,:19]
    df_dash = sample.iloc[:,-3:]

    if ddqn.state_dim == 9:
        # Extract the 9 clean physical telemetry features:
        # [q1, dt1, q2, dt2, q3, dt3, buffer, fps, bitrate]
        if 'deq_qdepth1' in sample.columns:
            feat_9 = sample[['deq_qdepth1', 'deq_timedelta1', 'deq_qdepth2', 'deq_timedelta2', 'deq_qdepth3', 'deq_timedelta3', 'bufferLocal', 'FPS', 'BitrateCalc']].values
        else:
            q1 = sample.iloc[:, 18].values
            dt1 = sample.iloc[:, 17].values
            q2 = sample.iloc[:, 12].values
            dt2 = sample.iloc[:, 11].values
            q3 = sample.iloc[:, 6].values
            dt3 = sample.iloc[:, 5].values
            buf = sample.iloc[:, -2].values
            fps = sample.iloc[:, -3].values
            br = sample.iloc[:, -1].values
            feat_9 = np.column_stack([q1, dt1, q2, dt2, q3, dt3, buf, fps, br])
        env.observation_space = feat_9
        current_state = feat_9
        dash_state = df_dash.values
        state_dim = 9
    else:
        env.observation_space = df_INT.values
        current_state = env.observation_space
        dash_state = df_dash.values
        state_dim = df_INT.shape[1]

    training_start = datetime.datetime.now()
    print("Received state, entering in the loop steps: {0}\n".format(training_start), end='\r')

    action = ddqn.epsilon_greedy_policy(current_state[FOURTH_SECOND].reshape(-1, state_dim))

    current_state, next_state, reward, done, _ = env.take_action(action, current_state, dash_state)
    print(reward)

    if next_state is not None and len(env.actions_history) >= 2:
        print("next state received, memorizing transition", end='\r')

        ddqn.memorize_transition(current_state[FOURTH_SECOND],
                                 env.actions_history[-2], #action performed before reward
                                 reward,
                                 next_state[FOURTH_SECOND],
                                 0.0 if done else 1.0)

        if ddqn.train:
            ddqn.experience_replay()
        
    
    training_end = datetime.datetime.now()
    print("Exiting the loop steps: {0}".format(training_end), end='\r')

    print("\n========================================\n", end='\r')
    print("last action: {0} | reward: {1} | fps: {2} | "
          "Target_Delay (sw1): {3:.0f} | Target_Delay(sw2): {4} | Target_Delay(sw3): {5}".format(
           env.actions_history[-1], env.reward_history[-1],
           env.fps_history[-1], env.target_delay_history_sw1[-1], 
           env.target_delay_history_sw2[-1], env.target_delay_history_sw3[-1]), end='\r')
    print("\n========================================\n", end='\r')

    save_training_logs(env, ddqn, experiment_id)



def jointoRl(sample, t):
    with join_lock:
        _jointoRl_unlocked(sample, t)


def _jointoRl_unlocked(sample, t):
    global sampleJoin
    global last_joined_timestamp

    window_size = 4
    max_age_seconds = 120

    # Retain each source's rows by their actual whole-second timestamp.
    rows = sample.sort_values('timestamp').drop_duplicates(
        subset='timestamp', keep='last'
    )

    for _, row in rows.iterrows():
        timestamp = int(row['timestamp'])
        if timestamp > last_joined_timestamp:
            sampleJoin[t][timestamp] = row.to_dict()

    int_buffer = sampleJoin[INT_TYPE]
    dash_buffer = sampleJoin[DASH_TYPE]

    while True:
        shared = sorted(set(int_buffer) & set(dash_buffer))
        matched = None

        for index in range(len(shared) - window_size + 1):
            candidate = shared[index:index + window_size]
            if candidate[-1] - candidate[0] == window_size - 1:
                matched = candidate
                break

        if matched is None:
            break

        int_window = pd.DataFrame([int_buffer[ts] for ts in matched])
        dash_window = pd.DataFrame([dash_buffer[ts] for ts in matched])

        int_window = int_window.sort_values('timestamp').reset_index(drop=True)
        dash_window = dash_window.sort_values('timestamp').reset_index(drop=True)

        if int_window['timestamp'].tolist() != dash_window['timestamp'].tolist():
            raise RuntimeError("INT/DASH timestamp join mismatch")

        dash_features = dash_window.drop(columns=['timestamp'])
        df = pd.concat([int_window, dash_features], axis=1)

        if df.shape[0] != window_size or df['FPS'].isna().any():
            raise RuntimeError("Invalid matched INT/DASH window")

        print(f"Sending timestamp-matched sample to RL (seconds={matched})")
        sendtoRl(df)

        # Consume the matched window and any older, skipped seconds.
        last_joined_timestamp = matched[-1]
        for buffer in (int_buffer, dash_buffer):
            for ts in list(buffer):
                if ts <= last_joined_timestamp:
                    del buffer[ts]

    # Bound the buffers when one source has missing or late samples.
    if int_buffer and dash_buffer:
        cutoff = min(max(int_buffer), max(dash_buffer)) - max_age_seconds
        for buffer in (int_buffer, dash_buffer):
            for ts in list(buffer):
                if ts < cutoff:
                    del buffer[ts]

def removeFeaturesSameValue(dataset):

    dataset.drop(columns=['switchID_t3','ingress_port3','egress_port3','egress_spec3',
                          'switchID_t2','ingress_port2','egress_port2','egress_spec2',
                          'switchID_t1','ingress_port1','egress_port1','egress_spec1'], inplace=True)
    return dataset

def changeNaNtoMean(dataset):

    dataset = dataset.fillna(dataset.mean())

    return dataset

def AggregatedSampleINT(aggregatedSample):
    global aggregatedINT

    observationSpace = 4
 
    if True:
        
        aggregatedSample = removeFeaturesSameValue(aggregatedSample)
        aggregatedSample['timestamp'] = (aggregatedSample['timestamp'] // 1000).astype(int)
        aggregatedINT = pd.concat([aggregatedINT, aggregatedSample], ignore_index=True)
        
        print(f'[DEBUG INT] rows={len(aggregatedINT)} unique_ts={aggregatedINT["timestamp"].nunique()}', end='\r')
        if aggregatedINT['timestamp'].nunique() >= observationSpace:
            print('[DEBUG] INT reached 4 unique timestamps, calling jointoRl')
            jointoRl(aggregatedINT, t=INT_TYPE)
            aggregatedINT = aggregatedINT[0:0]


def AggregatedSampleDash(aggregatedSample):
    global aggregatedDash

    observationSpace = 4

    aggregatedSample['timestamp'] = aggregatedSample['timestamp'].astype('int64') // 1000   # <-- replaced str[:10]+astype(int)

    if True:
        aggregatedDash = pd.concat([aggregatedDash, aggregatedSample], ignore_index=True)

        print(f'[DEBUG DASH] rows={len(aggregatedDash)} unique_ts={aggregatedDash["timestamp"].nunique()}', end='\r')
        if aggregatedDash['timestamp'].nunique() >= observationSpace:
            print('[DEBUG] DASH reached 4 unique timestamps, calling jointoRl')
            jointoRl(aggregatedDash, t=DASH_TYPE)
            aggregatedDash = aggregatedDash[0:0]


def dashMetrics(line):
    np.set_printoptions(precision=2, formatter={'float_kind':'{:16.2f}'.format})

    if len(line.split(";")[0]) != 13:          # <-- changed from 14 to 13
        DataDashZero = {'timestamp': [str(0)],
                        'FPS': [0],
                        'bufferLocal': [0],
                        'BitrateCalc': [0]}
        sampleDashZero = pd.DataFrame.from_dict(DataDashZero)
        AggregatedSampleDash(sampleDashZero)
    else:
        DataDash = {'timestamp': [str(line.split(";")[0])],
                'FPS': [float(line.split(";")[2])],
                'bufferLocal':  [float(line.split(";")[1])],
                'BitrateCalc': [float(line.split(";")[3])]}
        sampleDash = pd.DataFrame.from_dict(DataDash)
        AggregatedSampleDash(sampleDash)

def intMetrics(line):
    np.set_printoptions(precision=2, formatter={'float_kind':'{:16.2f}'.format})
    
    global sampleINT
    global count
    
    INTnames = ['timestamp','switchID_t3','ingress_port3','egress_port3','egress_spec3','ingress_global_timestamp3','egress_global_timestamp3',
                'enq_timestamp3','enq_qdepth3','deq_timedelta3','deq_qdepth3','switchID_t2','ingress_port2','egress_port2','egress_spec2',
                'ingress_global_timestamp2','egress_global_timestamp2','enq_timestamp2','enq_qdepth2','deq_timedelta2','deq_qdepth2',
                'switchID_t1','ingress_port1','egress_port1','egress_spec1','ingress_global_timestamp1','egress_global_timestamp1','enq_timestamp1',
                'enq_qdepth1','deq_timedelta1','deq_qdepth1'] 
    
    Data = StringIO(line)
    sampleINT_temp = pd.read_csv(Data, sep=",", names=INTnames)

    # Check if is a new second. If yes, start a count
    if  len(sampleINT) == 0:
        sampleINT = sampleINT_temp

    # Check if the sample is in the same second. If yes, 
    # add this new sample in the current matrix
    elif sampleINT.iloc[-1]['timestamp'] == sampleINT_temp.iloc[-1]['timestamp']:
        sampleINT = pd.concat([sampleINT, sampleINT_temp], ignore_index=True)
    
    # Check if the new sample is the next second. If yes,
    # send the current matrix to the next stages and restart
    # the process
    else:

        AggregatedSampleINT(sampleINT)
        sampleINT = sampleINT_temp


def getDashMetrics():
    global experiment_id
    path='/home/p4/DESiRED/src/logs/campaign_v2/dash_{0}.txt'.format(experiment_id)
    t = tail.Tail(path)
    t.register_callback(dashMetrics)
    t.follow(s=0.1)


def getINTMetrics():
    global experiment_id
    path='/home/p4/DESiRED/src/logs/campaign_v2/log_INT_{0}.txt'.format(experiment_id)
    t = tail.Tail(path)
    t.register_callback(intMetrics)
    t.follow(s=0.1)


def instantiateDQN(state_dim=19, online_network_filepath=None, target_network_filepath=None):
    gamma = .99  # discount factor
    tau = 10000     # target network update frequency.
    
    if state_dim == 9:
        architecture = (32, 32)
        if online_network_filepath is None:
            online_network_filepath = 'agent_models_fixed/online_network_retrained_balanced.h5'
        if target_network_filepath is None:
            target_network_filepath = 'agent_models_fixed/online_network_retrained_balanced.h5'
    else:
        architecture = (24, 24)  # units per layer
        if online_network_filepath is None:
            online_network_filepath = 'agent_models/online_network_train_socket_load_1.h5'
        if target_network_filepath is None:
            target_network_filepath = 'agent_models/target_network_train_socket_load_1.h5'
    
    learning_rate = 1e-3     # learning rate (default 1e-3)
    l2_reg = 1e-6            # L2 regularization
    
    replay_capacity = int(1e6)
    batch_size = 32
    minimum_experience_memory = 100 
    
    epsilon_start = 0.0
    epsilon_end = 0.0
    epsilon_decay_steps = 250 # 250 default
    epsilon_exponential_decay = .99

    num_actions = 3
    initialization = 'pretrained' # standard or pretrained
    experiment_type = 2           # 1 - train the dqn; 2 - inference only

    ddqn = DDQN(state_dim=state_dim,
                num_actions=num_actions,
                learning_rate=learning_rate,
                gamma=gamma,
                epsilon_start=epsilon_start,
                epsilon_end=epsilon_end,
                epsilon_decay_steps=epsilon_decay_steps,
                epsilon_exponential_decay=epsilon_exponential_decay,
                replay_capacity=replay_capacity,
                architecture=architecture,
                l2_reg=l2_reg,
                tau=tau,
                batch_size=batch_size,
                minimum_experience_memory=minimum_experience_memory,
                initialization=initialization,
                online_network_filepath=online_network_filepath,
                target_network_filepath=target_network_filepath,
                experiment_type=experiment_type)

    return ddqn


def save_training_logs(environment, agent, experiment_id):
    with open('agent_logs/campaign_v2/action_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.actions_history))

    with open('agent_logs/campaign_v2/reward_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.reward_history))
    
    with open('agent_logs/campaign_v2/fps_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.fps_history))
    
    with open('agent_logs/campaign_v2/sw1_target_delay_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.target_delay_history_sw1))
    
    with open('agent_logs/campaign_v2/sw2_target_delay_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.target_delay_history_sw2))
    
    with open('agent_logs/campaign_v2/sw3_target_delay_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.target_delay_history_sw3))
    
    with open('agent_logs/campaign_v2/loss_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], agent.losses))
    
    with open('agent_logs/campaign_v2/q-values_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x] if not isinstance(x, (list, tuple, np.ndarray)) else list(x), agent.q_values))


def main():
    
    global sampleINT
    global aggregatedINT
    global aggregatedDash
    global sampleJoin
    global last_joined_timestamp
    global count
    global ddqn
    global env
    global experiment_id

    parser = argparse.ArgumentParser(description="Experiment execution",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("number", type=str, help="Number of executions")
    parser.add_argument("type", type=str, help="TD, iRED, iRED-RL")
    parser.add_argument("--duration", type=int, default=700, help="Duration of experiment in seconds")
    parser.add_argument("--state-dim", type=int, default=19, choices=[9, 19], help="State dimension: 19 (legacy) or 9 (physical domain scaled)")
    parser.add_argument("--model-path", type=str, default=None, help="Path to online model h5")
    parser.add_argument("--initial-delay", type=int, default=DEFAULT_TARGET_DELAY, help="Initial target delay in us")
    args = parser.parse_args()
    
    config = vars(args)
    
    experiment_id = config['type']+"_"+config['number']

    print(f"Set initial Target Delay in switches: {args.initial_delay} us")
    for port in [9092, 9091, 9090]:
        cmd = f"echo 'register_write MyEgress.targetDelay_reg 0 {args.initial_delay}' | simple_switch_CLI --thrift-port {port} --thrift-ip 127.0.0.1"
        subprocess.run(cmd, shell=True)
    

    np.set_printoptions(precision=2)

       
    INTnames = ['timestamp','ingress_global_timestamp3','egress_global_timestamp3','enq_timestamp3','enq_qdepth3','deq_timedelta3','deq_qdepth3', 
                'ingress_global_timestamp2','egress_global_timestamp2','enq_timestamp2','enq_qdepth2','deq_timedelta2','deq_qdepth2',
                'ingress_global_timestamp1','egress_global_timestamp1','enq_timestamp1', 'enq_qdepth1','deq_timedelta1','deq_qdepth1'] 
    
    DASHnames = ['timestamp','FPS','bufferLocal','BitrateCalc']
    count = 0
    sampleINT = np.array([])
    sampleJoin = {INT_TYPE: {}, DASH_TYPE: {}}
    last_joined_timestamp = -1
    aggregatedINT = pd.DataFrame([], columns=INTnames)
    aggregatedDash = pd.DataFrame([], columns=DASHnames)

    ddqn = instantiateDQN(state_dim=args.state_dim, online_network_filepath=args.model_path, target_network_filepath=args.model_path)
    env = ControlPlaneEnvironment(sampleJoin, initial_delay=args.initial_delay)
    
    dashthread = threading.Thread(target=getDashMetrics, daemon=True)
    dashthread.start()

    intthread = threading.Thread(target=getINTMetrics, daemon=True)
    intthread.start()

    time.sleep(args.duration)

    save_training_logs(env, ddqn, experiment_id)
    ddqn.save_agent(experiment_id)
    print("logs saved")
     
if __name__ == '__main__':
    main()
