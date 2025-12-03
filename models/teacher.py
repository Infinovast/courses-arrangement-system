from dataclasses import dataclass

@dataclass
class Teacher:  # 教师类
    id:str     # 教师的唯一标识符
    name:str   # 教师姓名
    is_campus_teacher:bool   # 该教师是否为其他校区的教师

    def __hash__(self):
        return hash(self.id)