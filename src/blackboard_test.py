from blackboard import NovelBlackboard
import time
import threading

import os
"""
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe
docker start novelBlackboard_redis
"""

print(f"当前运行目录: {os.getcwd()}")

def mock_agent_listener():
    bb =    NovelBlackboard(port=63799)
    #返回的generator会阻塞监听，等有新消息才进入循环,这里的消息是字典
    #redis广播的message是{type：'message', data:'{event:event_name,payload:payload}'}
    for message in bb.subscribe_events():
        if message['type'] == 'message' :
            import json
            #字典的值是个纯文本json,要再转化成字典
            data = json.loads(message['data'])
            if data['event'] == 'AGENDA_READY':
                print('\n[Agent 收到指令] 开始写初稿')
                agenda = bb.get_data("workspace.Agenda")
                print(f'[Agent 读取黑板] 本章细纲内容是:{agenda}')
                break

if __name__ == "__main__":
    listener_thread = threading.Thread(target=mock_agent_listener)
    listener_thread.start()
    
    time.sleep(1)

    print("开始运行小说生成器")
    master_bb = NovelBlackboard(port=63799)
    master_bb.clear_workspace()
    master_bb.set_data("workspace.Agenda", '迎着阳光盛大逃亡')
    print('大纲完成，进行AGENDA_READY播报')
    master_bb.publish_event('AGENDA_READY')

    listener_thread.join()

    print('AGENDA_READY测试播报已完成')