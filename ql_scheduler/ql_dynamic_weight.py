import pickle
import os
import random
from collections import defaultdict


class QLearningWeightOptimizer:

    def __init__(self, q_table_path='q_table_weights.pkl'):
        # 修正Q表保存路径为当前工作目录
        self.q_table_path = os.path.join(os.getcwd(), q_table_path)

        # Q-learning参数
        self.alpha = 0.1  # 学习率
        self.gamma = 0.9  # 折扣因子
        self.epsilon = 0.3  # 初始探索率
        self.epsilon_min = 0.05  # 最小探索率
        self.epsilon_decay = 0.995  # 探索率衰减

        # 动作空间：不同的软约束权重值
        self.actions = [0.1, 0.3, 0.5, 0.7, 1.0]

        # Q表
        self.q_table = defaultdict(lambda: {action: 0.0 for action in self.actions})

        # 学习状态追踪
        self.episode_count = 0  # episode计数（每次完整运行算一个episode）
        self.current_state = None
        self.current_action = None
        self.last_penalty = None
        self.penalty_history = []  # 记录惩罚值历史

        # 加载已有的Q表
        self._load_q_table()

    def _load_q_table(self):
        if os.path.exists(self.q_table_path):
            try:
                with open(self.q_table_path, 'rb') as f:
                    data = pickle.load(f)
                    loaded_q_table = data['q_table']

                    # 将加载的普通dict转换为defaultdict
                    self.q_table = defaultdict(lambda: {action: 0.0 for action in self.actions})
                    for state, actions in loaded_q_table.items():
                        self.q_table[state] = actions.copy()

                    self.episode_count = data.get('episode_count', 0)
                    self.epsilon = max(self.epsilon_min,
                                       self.epsilon * (self.epsilon_decay ** self.episode_count))
                print(f"成功加载Q表，包含 {len(loaded_q_table)} 个状态，已完成 {self.episode_count} 个episode")
            except Exception as e:
                print(f"加载Q表失败: {e}，将使用新的Q表")
        else:
            print("未找到已有Q表，将创建新的Q表")

    def save_q_table(self):
        """保存Q表到文件"""
        try:
            with open(self.q_table_path, 'wb') as f:
                pickle.dump({
                    'q_table': dict(self.q_table),
                    'episode_count': self.episode_count,
                }, f)
            print(f"Q表已保存到 {self.q_table_path}，包含 {len(self.q_table)} 个状态")
        except Exception as e:
            print(f"保存Q表失败: {e}")

    def _get_state(self, generation, max_generation, penalty):
        # 1. 代数阶段
        progress = generation / max_generation
        if progress < 0.2:
            generation_phase = 0  # 早期
        elif progress < 0.8:
            generation_phase = 1  # 中期
        else:
            generation_phase = 2  # 后期

        # 2. 硬约束冲突程度
        if penalty < 5000:
            hard_conflict_level = 0  # 无硬约束冲突
        elif penalty < 10000:
            hard_conflict_level = 1  # 低
        elif penalty < 20000:
            hard_conflict_level = 2  # 中
        else:
            hard_conflict_level = 3  # 高

        # 3. 软约束违反程度
        if penalty < 1000:
            soft_conflict_level = 0  # 几乎无软约束违反
        elif penalty < 3000:
            soft_conflict_level = 1  # 低
        elif penalty < 5000:
            soft_conflict_level = 2  # 中
        else:
            soft_conflict_level = 3  # 高

        # 4. 优化速度
        if len(self.penalty_history) < 2:
            progress_speed = 1  # 缓慢
        else:
            recent_improvement = self.penalty_history[-2] - self.penalty_history[-1]
            improvement_rate = recent_improvement / max(self.penalty_history[-2], 1)

            if improvement_rate > 0.1:
                progress_speed = 0  # 快速下降
            elif improvement_rate > 0.01:
                progress_speed = 1  # 缓慢下降
            elif improvement_rate > -0.01:
                progress_speed = 2  # 停滞
            else:
                progress_speed = 3  # 波动

        return (generation_phase, hard_conflict_level, soft_conflict_level, progress_speed)

    def _calculate_reward(self, old_penalty, new_penalty):
        reward = 0.0

        # 估算硬约束部分
        old_hard = max(0, old_penalty - 5000)
        new_hard = max(0, new_penalty - 5000)

        # 硬约束奖励
        hard_improvement = old_hard - new_hard
        if hard_improvement > 0:
            reward += 100 * (hard_improvement / 1000)
        elif hard_improvement < 0:
            reward -= 50 * (-hard_improvement / 1000)

        # 无硬约束额外奖励
        if new_penalty < 5000:
            reward += 200

        # 软约束奖励
        if new_penalty < 5000 and old_penalty < 5000:
            soft_improvement = old_penalty - new_penalty
            if soft_improvement > 0:
                reward += 50 * (soft_improvement / 1000)
            elif soft_improvement < 0:
                reward -= 25 * (-soft_improvement / 1000)

        # 进度奖励
        total_improvement = old_penalty - new_penalty
        improvement_rate = total_improvement / max(old_penalty, 1)

        if improvement_rate > 0.1:
            reward += 30
        elif improvement_rate > 0.05:
            reward += 10
        elif abs(improvement_rate) < 0.01:
            reward -= 10

        return reward

    def choose_action(self, state):
        # ε-greedy策略
        if random.random() < self.epsilon:
            action = random.choice(self.actions)
        else:
            q_values = self.q_table[state]
            max_q = max(q_values.values())
            best_actions = [a for a, q in q_values.items() if q == max_q]
            action = random.choice(best_actions)

        return action

    def update_q_table(self, state, action, reward, next_state):
        """更新Q表"""
        current_q = self.q_table[state][action]

        next_state_q_values = self.q_table[next_state]
        max_next_q = max(next_state_q_values.values()) if next_state_q_values else 0.0

        new_q = current_q + self.alpha * (reward + self.gamma * max_next_q - current_q)
        self.q_table[state][action] = new_q

    def start_episode(self):
        self.episode_count += 1
        self.penalty_history = []
        self.last_penalty = None
        self.current_state = None
        self.current_action = None

        # 衰减epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        print(f"Q-learning Episode {self.episode_count} 开始，ε={self.epsilon:.3f}")

    def end_episode(self):
        self.save_q_table()
        print(f"Q-learning Episode {self.episode_count} 结束")

    def get_soft_constraint_weight(self, generation, max_generation, penalty):
        """获取当前软约束权重（主接口）"""
        # 获取当前状态
        current_state = self._get_state(generation, max_generation, penalty)

        # 更新Q表（如果不是第一次调用）
        if self.current_state is not None and self.last_penalty is not None:
            reward = self._calculate_reward(self.last_penalty, penalty)
            self.update_q_table(self.current_state, self.current_action, reward, current_state)

        # 选择新动作
        action = self.choose_action(current_state)

        # 更新状态追踪
        self.current_state = current_state
        self.current_action = action
        self.last_penalty = penalty
        self.penalty_history.append(penalty)

        return action

    def get_statistics(self):
        """获取统计信息"""
        avg_q = 0.0
        if len(self.q_table) > 0:
            all_q_values = []
            for state_q in self.q_table.values():
                all_q_values.extend(state_q.values())
            avg_q = sum(all_q_values) / len(all_q_values) if all_q_values else 0.0

        return {
            'episode': self.episode_count,
            'epsilon': self.epsilon,
            'q_table_size': len(self.q_table),
            'average_q_value': avg_q,
            'current_weight': self.current_action if self.current_action else 0.1,
        }


class QLearningWeightWrapper:
    """简化接口包装类"""

    def __init__(self):
        self.optimizer = QLearningWeightOptimizer()

    def start_episode(self):
        self.optimizer.start_episode()

    def end_episode(self):
        self.optimizer.end_episode()

    def get_soft_constraint_weight(self, generation, max_generation, penalty):
        return self.optimizer.get_soft_constraint_weight(generation, max_generation, penalty)

    def get_statistics(self):
        return self.optimizer.get_statistics()