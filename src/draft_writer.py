import json
import os
import time
from blackboard import NovelBlackboard
from openai import OpenAI
from dotenv import load_dotenv

#根据选择的大模型还要import相应的大模型的包
""" 

cd C:\project\generateNovel\src
python draft_writer.py

"""


class DraftWriter:
    def __init__(self):
        self.bb = NovelBlackboard(port=63799)
        self.system_prompt = """你是顶尖的小说作家，你擅长思考社会、经济、人文，兼具大气、细腻等等风格的多样文笔，
        你的任务是根据系统提供的【L0 核心记忆】以及【本章细纲】，扩写出一段逻辑自洽、细节生动、符合当前情绪节奏的小说初稿。

⚠️ 核心写作准则：严格遵循“剧情阶段 (Arc Phase)”约束
* 【起】（铺垫期）：放慢节奏，注重环境描写，引入谜团或危机，不要有激烈战斗。
* 【承】（发展期）：加快节奏，注重交锋，压抑情绪，让主角遭遇阻力。
* 【转】（高潮期）：极快节奏，多用短句，动作凌厉，底牌尽出，斩断阻碍。
* 【合】（尾声期）：舒缓悠长，盘点收获，安抚情绪，埋下下一卷的伏笔。

请无需任何寒暄或解释，直接输出排版优美、分段合理的小说纯文本正文。"""

        load_dotenv()
        # ==========================================
        # 🎛️ 核心开关：在这里切换测试/实战模式
        # ==========================================
        # self.use_mock_llm = True
        self.use_mock_llm = False
        self.temperature = 0.9
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.model_name = "qwen3-max-preview"


        if not self.use_mock_llm:
            try:

                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )   
                print("确定api_key,temperature及base_url")
            except ImportError:
                print("❌ 未安装 openai 库！请在终端运行: pip install openai")

    
    #调用大模型,分为模拟与实际调用
    def call_llm(self, prompt):

        #1.模拟
        if self.use_mock_llm:
            print("\n⏳ [初稿引擎]已进入撰写阶段")
            time.sleep(2)

            # === 模拟返回结果 ===
            mock_result = f"""
        烈日当空，空气被炙烤得微微扭曲。
        
        “迎着阳光盛大逃亡……”他嘴里反复咀嚼着这句不知从哪听来的话，脚下的步伐却一点不敢放慢。
        身后，尖锐的警报声和刺耳的引擎轰鸣正像附骨之疽般死死咬着他不放。汗水模糊了视线，但他知道自己不能停下，哪怕前面是万丈深渊。
        只要穿过这片废墟，那辆接应的破旧悬浮车就在那里。
        
        （这是由初稿引擎基于细纲扩写的一段初稿文本。）
    """     
            return mock_result
        #2.实际调用
        else:
            print(f"\n[初稿引擎] 正在使用{self.model_name}进行初稿撰写...")
            try:
                #在llm客户端，选择对话模式，补全功能，创建任务
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role":"system","content":self.system_prompt},
                        {"role":"user","content":prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=3000
                )
                print(f"收到的message为:{response}")
                return response.choices[0].message.content
            except Exception as e:
                error_type = type(e).__name__
                error_detail = str(e)

                # 💡 统一处理报错信息
                if "AuthenticationError" in error_type:
                    msg = "[错误]API Key 无效或已过期"
                elif "RateLimitError" in error_type:
                    msg = "[错误]达到频率限制/余额不足"
                elif "APITimeoutError" in error_type:
                    msg = "[错误]连接超时"
                else:
                    msg = f"[未知错误]{error_type}: {error_detail}"
                
                print(msg)
                return msg  # ✅ 关键：必须返回这个字符串，防止返回 None

    def run(self):
        mode_str = "模拟模式" if self.use_mock_llm else "调用模式"
        print(f"🖋️ [初稿引擎] 已启动，当前模式{mode_str}，正在等待大纲指令...")

        #1. 监听请求后,从黑板拉取数据
        try:
            for message in self.bb.subscribe_events():
                if message['type'] == 'message':
                    import json
                    data = json.loads(message['data'])

                    if data['event'] == 'AGENDA_READY':
                        print("\n🎯 [初稿引擎] 已收到AGENDA_READY指令！")

                        agenda = self.bb.get_data('workspace.Agenda')
                        l0_memory = self.bb.get_data("workspace.Memory_L0")
                        if not l0_memory:
                            l0_memory = '暂无前文背景（故事正待开篇）'

                        print(f"读取大纲内容如下：\n{agenda}")

                        #2. 完成大纲读取后，拼接提示词，调用大模型
                        prompt = f"[前文背景]\n{l0_memory}\n\n[本章细纲]\n{agenda}\n\n请开始正文撰写"
                        draft_text = self.call_llm(prompt)

                        #3. 写入黑板
                        self.bb.set_data('workspace.Draft',draft_text)
                        print(f"\n[初稿引擎]初稿撰写完毕，已写入黑板,初稿内容如下{draft_text}")

                        preview = draft_text[:100] + "..." if len(draft_text)>100 else draft_text
                        print(f"内容预览：{preview}")


                        #4. 发布事件,把字数一起发了
                        self.bb.publish_event('DRAFT_READY', payload={"word_count":len(draft_text)})
        except KeyboardInterrupt:
            print("\n已检测退出信号")
        finally:
            print("🏠 已彻底退出。")

if __name__ == "__main__":
    writer = DraftWriter()
    writer.run()