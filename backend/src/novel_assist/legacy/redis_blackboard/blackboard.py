import redis
import json

class NovelBlackboard:

    """
    这是客户端,连接redis数据库的
    """

    def __init__(self,host='localhost', port=63799, db=0):
        
        #这里的r不是子函数是一个redis实例,用来连接redis数据库"
        self.r = redis.Redis(host=host, port=port, db=0, decode_responses=True)

        #使这个示例加上订阅功能,就是给subscribe_event用的,固定下来，如果在别的地方先self.r.pubsub(self.channel)来定义的话，在别地方再self.r.pubsub().listen或者别的方法会新建一个pubsub实例，那频道就不对了，所以创建一个self.publish，固定频道
        self.pubsub = self.r.pubsub()

        #创建字符串对象，方便以后直接用而不是再打一遍具体名字"
        self.workspace_key = "novel:workspace:current" #用来确定当前是哪个workspace的，之后可能有多个书就有多个workspace
        self.channel = "novel_events"

    #workspace_key键值对的键，键对应的值里面的json的栏目"

    def set_data(self, field, value):

        #如果value是dict或者list才true,在这种情况下把这俩转化成纯文本字符串，不然redis的db收不进去(键值对都只能是字符串)"
        if isinstance(value, (dict,list)):
            value = json.dumps(value, ensure_ascii=False)

        "redis哈希表写入,写入位置"
        self.r.hset(self.workspace_key, field, value)
    
    def get_data(self, field):
        #哈希查询,可能获得None,纯文本或者JSON
        val = self.r.hget(self.workspace_key, field)

        if not val:
            return None
        try:
            #把纯文本尝试还原成
            return json.loads(val)
            #如果解压失败，防止报错崩溃直接给回该纯文本
        except json.JSONDecodeError:
            return val
    
    #全删
    def clear_workspace(self):
        self.r.delete(self.workspace_key)
        print("🧹 [黑板清空] 准备迎接新章节。")

    def publish_event(self, event_name, payload=None):
        message = {"event":event_name, "payload":payload}
        #使用redis实例的发布方法,在特定频道发送字符串，测试时用的是agenda——ready
        self.r.publish(self.channel, json.dumps(message, ensure_ascii=False))
        print(f"[事件广播]{event_name}")
    
    def subscribe_events(self):
        self.pubsub.subscribe(self.channel)
        print(f"[事件监听]:开始监听频道:{self.channel}")

        #redis.Redis.pubsub(参数).listen()生成一个一直卡住等待新消息的生成器，有消息就返回该消息
        return self.pubsub.listen()