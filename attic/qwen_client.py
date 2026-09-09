import os
import json
import base64
from io import BytesIO
from openai import OpenAI
from PIL import ImageGrab

# Configuration
# Default local server port for LM Studio is 1234
LM_STUDIO_URL = "http://localhost:1234/v1"

# LM Studio generally ignores the model name as long as one is loaded, 
# but "local-model" is a safe default.
MODEL_NAME = "local-model"  

client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

# Global conversation history
messages = []

# --- Tool Definitions ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "clear_context_and_restart",
            "description": "CRITICAL TOOL: Clears your entire conversation history to free up context window and restarts your persona with a new focus. Use this when transitioning between major phases (e.g., from Analysis to Planning, or Planning to Implementation). Before calling this, ensure you have saved any necessary information to a file (like analysis.md or plan.md) so you can read it back after restarting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phase_name": {
                        "type": "string", 
                        "description": "Name of the new phase (e.g., 'Planning', 'Implementation', 'Review')"
                    },
                    "new_system_prompt": {
                        "type": "string", 
                        "description": "Your new system prompt for this phase. Example: 'You are now in the Planning phase. Your goal is to read the analysis and write a step-by-step plan.'"
                    },
                    "initial_instruction": {
                        "type": "string", 
                        "description": "The very first message you will receive upon restart. Example: 'Please read analysis_checkpoint.md and output a plan.'"
                    }
                },
                "required": ["phase_name", "new_system_prompt", "initial_instruction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Takes a screenshot of the main computer screen and provides it to you as an image. Use this to visually evaluate UI, errors, or program output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why you need the screenshot."}
                },
                "required": ["reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the content of a local file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative or absolute path to the file."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes text content to a local file. Overwrites existing content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative or absolute path to the file."},
                    "content": {"type": "string", "description": "The text content to write."}
                },
                "required": ["file_path", "content"]
            }
        }
    }
]

def init_chat():
    global messages
    messages = [
        {
            "role": "system", 
            "content": "You are an autonomous AI Engineer powered by Qwen. You have access to tools to read/write files, take screenshots, and clear your own context window. Always save your findings to files (like analysis.md or plan.md) BEFORE clearing your context to move to the next phase."
        }
    ]

def handle_tool_call(tool_call):
    global messages
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except Exception:
        args = {}
        
    print(f"\n[Agent called tool: {name}]")
    
    if name == "clear_context_and_restart":
        print(f"\n==================================================")
        print(f"🔄 RESTARTING CONTEXT: Entering Phase -> {args.get('phase_name', 'Unknown')}")
        print(f"==================================================\n")
        
        # Completely overwrite the message history with the new context
        messages = [
            {"role": "system", "content": args.get("new_system_prompt", "You are an AI assistant.")},
            {"role": "user", "content": args.get("initial_instruction", "Please continue.")}
        ]
        return "CONTEXT_CLEARED"
        
    elif name == "take_screenshot":
        try:
            screenshot = ImageGrab.grab()
            buffered = BytesIO()
            screenshot.save(buffered, format="JPEG", quality=70) # Quality 70 keeps size low for API
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            # OpenAI vision format requires images to be passed inside user messages
            return {
                "type": "image",
                "text": f"Screenshot taken for: {args.get('reason')}",
                "image_base64": img_str
            }
        except Exception as e:
            return f"Screenshot failed: {str(e)}"
            
    elif name == "read_file":
        try:
            with open(args["file_path"], "r", encoding="utf-8") as f:
                content = f.read()
                print(f"-> Read {len(content)} characters from {args['file_path']}")
                return content
        except Exception as e:
            return f"Error reading file: {str(e)}"
            
    elif name == "write_file":
        try:
            with open(args["file_path"], "w", encoding="utf-8") as f:
                f.write(args["content"])
            print(f"-> Wrote to {args['file_path']}")
            return f"Successfully wrote to {args['file_path']}"
        except Exception as e:
            return f"Error writing file: {str(e)}"
    
    return "Unknown tool."

def main():
    global messages
    init_chat()
    print("==================================================")
    print("🤖 Qwen 3.5 LM Studio Agent Initialized")
    print("Features: File I/O, Screenshots, Context Clearing")
    print("Type 'exit' to quit.")
    print("==================================================\n")
    
    while True:
        # Get user input only if the last message was from the assistant (or it's the start)
        # If the last message was a tool, we let the AI respond to the tool immediately
        if not messages or messages[-1]["role"] not in ["tool", "system"]:
            # Check if we just did a context clear (last message is user instruction from the tool)
            if len(messages) == 2 and messages[0]["role"] == "system" and messages[1]["role"] == "user":
                pass # Don't ask for input, let the model process the auto-injected instruction
            else:
                user_input = input("\nYou: ")
                if user_input.lower() == 'exit':
                    break
                messages.append({"role": "user", "content": user_input})

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.3
            )
            
            msg = response.choices[0].message
            
            # Print agent's text response if it exists
            if msg.content:
                print(f"\nAgent: {msg.content}")
                
            messages.append(msg)
            
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    result = handle_tool_call(tool_call)
                    
                    if result == "CONTEXT_CLEARED":
                        # The tool wiped and replaced the 'messages' array. 
                        # We break this inner loop so it sends the fresh messages to the model.
                        break 
                        
                    elif isinstance(result, dict) and result.get("type") == "image":
                        # 1. Acknowledge tool call strictly for API schema satisfaction
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "Image provided in following user message."
                        })
                        # 2. Provide actual image as a user message
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": result["text"]},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{result['image_base64']}"
                                    }
                                }
                            ]
                        })
                    else:
                        # Standard text response from a tool
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result)
                        })
                        
        except Exception as e:
            print(f"\nAPI Error: {e}")
            print("Make sure LM Studio is running on port 1234, the server is started, and a model is loaded.")
            break

if __name__ == "__main__":
    main()
