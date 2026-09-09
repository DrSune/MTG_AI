import os
import sys
import json
import base64
import argparse
import re
from io import BytesIO
from openai import OpenAI
from PIL import ImageGrab

# --- Configuration ---
LM_STUDIO_URL = "http://localhost:1234/v1"
MODEL_NAME = "local-model"

client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

# Global conversation history
messages = []

# --- System Prompts for Phases ---
TOOL_GUIDE = (
    "\n\n### 🛠️ MANDATORY TOOL FORMAT:\n"
    "If you want to use a tool, you MUST use this format:\n"
    "TOOL: name\n"
    "ARGS: {\"key\": \"value\"}\n\n"
    "Example:\n"
    "TOOL: read_file\n"
    "ARGS: {\"file_path\": \"project_goals.md\"}\n\n"
    "TOOLS: list_directory, read_file, write_file, take_screenshot, clear_context_and_restart, terminate_session.\n"
    "\n### 🚨 FINALITY RULE:\n"
    "When you have completed the user's request, YOU MUST NOT SIMPLY TALK. "
    "You MUST call 'terminate_session' with a summary of your work. "
    "Failure to call this tool wastes electricity and CPU time."
)

MEMORY_POLICY = (
    "\n\n### 🧠 REFRESH RULE (Strategic Reasoning):\n"
    "1. CONTEXT SATURATION: After 5 turns, your 'reasoning quality' begins to drop as the window fills with tool results. "
    "To maintain Senior-level accuracy, you MUST refresh.\n"
    "2. CHECKPOINT: Every 4-5 tool calls, use 'write_file' to save a 'thought_checkpoint.md'. "
    "This file is your 'Long-Term Memory'. Include: Current objective, findings so far, and the next 3 steps.\n"
    "3. ACTION: Immediately after checkpointing, call 'clear_context_and_restart'. "
    "This is NOT an interruption; it is a STRATEGIC ADVANTAGE that allows you to approach the next sub-task with 100% focus and zero 'noise'.\n"
    "4. MANDATORY RESTART: If the user gives you a list of items (like files or tasks), restart every 3-4 items processed."
)

PHASE_PROMPTS = {
    "Analysis": "You are an AI Analyst. Identify constraints. Output to 'analysis_checkpoint.md'. " + TOOL_GUIDE + MEMORY_POLICY,
    "Planning": "You are a Software Architect. Create 'implementation_plan.md'. " + TOOL_GUIDE + MEMORY_POLICY,
    "Implementation": "You are a Senior Developer. Execute the plan. REFRESH your context every 5 steps. " + TOOL_GUIDE + MEMORY_POLICY,
    "Review": "You are QA. Verify with screenshots. If satisfied, you MUST call 'terminate_session' to end the process. " + TOOL_GUIDE + MEMORY_POLICY
}

# --- Tool Definitions ---
tools = [
    {"type": "function", "function": {"name": "clear_context_and_restart", "description": "Restarts with fresh context.", "parameters": {"type": "object", "properties": {"phase_name": {"type": "string", "enum": ["Analysis", "Planning", "Implementation", "Review"]}, "initial_instruction": {"type": "string"}}, "required": ["phase_name", "initial_instruction"]}}},
    {"type": "function", "function": {"name": "terminate_session", "description": "Exits program.", "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}},
    {"type": "function", "function": {"name": "take_screenshot", "description": "Takes screenshot.", "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Reads file.", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Writes file.", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "Lists directory.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}}}}
]

def handle_direct_call(name, args):
    global messages
    print(f"\n🛠️  EXECUTING: {name}({args})")
    
    if name == "terminate_session":
        print(f"\n✅ FINISHED: {args.get('reason', 'Done')}")
        sys.exit(0)

    if name == "clear_context_and_restart":
        phase = args.get("phase_name", "Analysis")
        print(f"\n🔄 REFRESHING -> Phase: {phase}")
        messages = [{"role": "system", "content": PHASE_PROMPTS.get(phase, PHASE_PROMPTS["Analysis"])}, {"role": "user", "content": args.get("initial_instruction", "Continue.")}]
        return "CONTEXT_CLEARED"
        
    try:
        if name == "take_screenshot":
            screenshot = ImageGrab.grab()
            buffered = BytesIO()
            screenshot.save(buffered, format="JPEG", quality=70)
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return {"type": "image", "text": args.get("reason", "N/A"), "image_base64": img_str}
        elif name == "read_file":
            with open(args["file_path"], "r", encoding="utf-8") as f: return f.read()
        elif name == "write_file":
            with open(args["file_path"], "w", encoding="utf-8") as f: f.write(args["content"])
            return f"Saved to {args['file_path']}"
        elif name == "list_directory":
            return str(os.listdir(args.get("path", ".")))
    except Exception as e:
        return f"Error: {str(e)}"
    return "Unknown tool."

def parse_hallucinated_calls(content):
    """Universal parser for Qwen's various tool call hallucinations."""
    calls = []
    
    # Pattern A: XML-like format (function=name, parameter=key>value)
    # Very loose regex to catch anything that looks like a parameter
    func_matches = re.finditer(r'function\s*=\s*([\w_]+)', content)
    for f in func_matches:
        f_name = f.group(1).strip()
        params = {}
        # Find everything between <parameter=key> and </parameter> or the next <
        p_matches = re.finditer(r'parameter\s*=\s*([\w_]+)>\s*([\s\S]*?)\s*(?:</parameter>|<|$)', content)
        for p in p_matches:
            params[p.group(1).strip()] = p.group(2).strip()
        if f_name: calls.append({"name": f_name, "args": params})

    # Pattern B: TOOL: name / ARGS: {json}
    text_matches = re.finditer(r'TOOL:\s*(\w+)\s*ARGS:\s*({.*?})', content, re.DOTALL)
    for t in text_matches:
        try: calls.append({"name": t.group(1), "args": json.loads(t.group(2))})
        except: pass

    # Pattern C: EXECUTE: name / PARAMS: {json}
    exec_matches = re.finditer(r'EXECUTE:\s*(\w+)\s*PARAMS:\s*({.*?})', content, re.DOTALL)
    for e in exec_matches:
        try: calls.append({"name": e.group(1), "args": json.loads(e.group(2))})
        except: pass

    # Pattern D: Raw JSON blocks
    json_blocks = re.findall(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    for block in json_blocks:
        try:
            data = json.loads(block)
            if "tool" in data: calls.append({"name": data["tool"], "args": data.get("parameters", {})})
            elif "name" in data and "args" in data: calls.append(data)
        except: pass

    return calls

def main():
    global messages
    parser = argparse.ArgumentParser()
    parser.add_argument("instruction", nargs="?")
    args = parser.parse_args()

    messages = [{"role": "system", "content": PHASE_PROMPTS["Analysis"]}]
    if args.instruction: messages.append({"role": "user", "content": args.instruction})
    else: 
        print("🤖 Qwen Ready.")
        messages.append({"role": "user", "content": input("📝 YOU: ")})

    while True:
        try:
            print("\n[Thinking...]")
            response = client.chat.completions.create(model=MODEL_NAME, messages=messages, tools=tools, tool_choice="auto", temperature=0.1)
            msg = response.choices[0].message
            
            if hasattr(msg, 'reasoning_content') and msg.reasoning_content: print(f"\n🧠 THOUGHTS:\n{msg.reasoning_content}")
            if msg.content: print(f"\n🤖 AGENT:\n{msg.content}")
            messages.append(msg)
            
            executed = False
            # 1. API Tools
            if msg.tool_calls:
                for t in msg.tool_calls:
                    executed = True
                    try: args = json.loads(t.function.arguments)
                    except: args = {}
                    res = handle_direct_call(t.function.name, args)
                    if res == "CONTEXT_CLEARED": break
                    if isinstance(res, dict) and res.get("type") == "image":
                        messages.append({"role": "tool", "tool_call_id": t.id, "content": "Sent."})
                        messages.append({"role": "user", "content": [{"type":"text","text":res["text"]},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{res['image_base64']}"}}]})
                    else:
                        print(f"📥 RESULT: {str(res)[:100]}...")
                        messages.append({"role": "tool", "tool_call_id": t.id, "content": str(res)})

            # 2. Universal Hallucination Parser
            # Model might hallucinate tool calls in 'content' OR 'reasoning_content'
            combined_text = (msg.content or "") + "\n" + (getattr(msg, 'reasoning_content', None) or "")
            if not executed and combined_text.strip():
                hallucinated = parse_hallucinated_calls(combined_text)
                if hallucinated:
                    for h in hallucinated:
                        executed = True
                        res = handle_direct_call(h["name"], h["args"])
                        if res == "CONTEXT_CLEARED": break
                        print(f"📥 RESULT: {str(res)[:100]}...")
                        # We send this back as a user message to trick the model into continuing
                        messages.append({"role": "user", "content": f"TOOL RESULT ({h['name']}): {res}"})

            if not executed:
                user_input = input("\n📝 YOU: ")
                if user_input.lower() in ['exit', 'quit']: break
                messages.append({"role": "user", "content": user_input})

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            break

if __name__ == "__main__":
    main()
