from dataclasses import dataclass

@dataclass(frozen=True,eq=True)
class Room:  # 机房类
    id:str   # 机房的唯一标识符
    name:str  # 机房名称

    def __hash__(self):
        return hash(self.id)