import requests
import subprocess
import os
import tempfile
import customtkinter as ctk
from tkinter import messagebox
import threading

OLLAMA_WINDOWS_URL = "https://ollama.com/download/OllamaSetup.exe"

class OllamaInstaller:
    def __init__(self):
        self.ollama_path = None
        self.find_ollama()
        
    def find_ollama(self):
        try:
            result = subprocess.run(
                ["where", "ollama"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.ollama_path = result.stdout.strip().split('\n')[0]
                return True
        except:
            pass
        return False
        
    def is_ollama_installed(self):
        return self.find_ollama()
        
    def is_ollama_running(self):
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
            
    def get_installed_models(self):
        if not self.is_ollama_running():
            return []
            
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
        except:
            pass
        return []
        
    def download_ollama_installer(self, progress_callback=None):
        try:
            if progress_callback:
                progress_callback("Descargando instalador de Ollama...")
                
            response = requests.get(OLLAMA_WINDOWS_URL, stream=True, timeout=30)
            response.raise_for_status()
            
            temp_dir = tempfile.gettempdir()
            installer_path = os.path.join(temp_dir, "OllamaSetup.exe")
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            percent = (downloaded / total_size) * 100
                            progress_callback(f"Descargando... {percent:.1f}%")
                            
            return installer_path
            
        except Exception as e:
            raise Exception(f"Error al descargar Ollama: {str(e)}")
            
    def install_ollama(self, installer_path, progress_callback=None):
        try:
            if progress_callback:
                progress_callback("Ejecutando instalador de Ollama...")
                
            subprocess.run([installer_path], check=True)
            
            if progress_callback:
                progress_callback("Instalación completada")
                
            self.find_ollama()
            return True
            
        except Exception as e:
            raise Exception(f"Error al instalar Ollama: {str(e)}")
            
    def start_ollama_service(self):
        try:
            if os.name == 'nt':
                subprocess.Popen(
                    ["ollama", "serve"],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                subprocess.Popen(["ollama", "serve"])
            return True
        except Exception as e:
            raise Exception(f"Error al iniciar Ollama: {str(e)}")

    def stop_ollama_processes(self):
        """Cierra todos los procesos de Ollama (app + servidor)."""
        killed = []
        errors = []

        if os.name == "nt":
            # Nombres típicos en Windows
            process_names = ["ollama.exe", "ollama app.exe", "Ollama.exe"]
            for name in process_names:
                try:
                    result = subprocess.run(
                        ["taskkill", "/F", "/IM", name, "/T"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    if result.returncode == 0:
                        killed.append(name)
                    elif "not found" not in (result.stderr or "").lower() and \
                         "no se encontró" not in (result.stderr or "").lower():
                        # Ignorar "proceso no encontrado"; reportar otros errores
                        if result.stderr and result.stderr.strip():
                            errors.append(f"{name}: {result.stderr.strip()}")
                except Exception as e:
                    errors.append(f"{name}: {e}")
        else:
            try:
                result = subprocess.run(
                    ["pkill", "-f", "ollama"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    killed.append("ollama")
            except Exception as e:
                errors.append(str(e))

        return {"killed": killed, "errors": errors}
            
    def pull_model(self, model_name, progress_callback=None):
        try:
            if progress_callback:
                progress_callback(f"Descargando modelo {model_name}...")
                
            process = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                if progress_callback:
                    progress_callback(line.strip())
                    
            process.wait()
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback(f"Modelo {model_name} descargado correctamente")
                return True
            else:
                raise Exception(f"Error al descargar el modelo: {process.stderr.read()}")
                
        except Exception as e:
            raise Exception(f"Error al descargar modelo: {str(e)}")

class OllamaSetupDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Configuración de Ollama")
        self.geometry("620x640")
        self.minsize(560, 520)
        self.resizable(True, True)
        
        self.attributes('-topmost', True)
        
        ctk.set_appearance_mode("dark")
        
        self.installer = OllamaInstaller()
        
        self.create_widgets()
        self.update_status()
        
    def create_widgets(self):
        # Contenedor con scroll para que ningún botón quede fuera de vista
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        header_frame = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=8)
        header_frame.pack(fill="x", padx=10, pady=(10, 12))
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="Asistente de Configuración de Ollama",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#00d9ff"
        )
        title_label.pack(pady=15)
        
        status_frame = ctk.CTkFrame(scroll, fg_color="#1a1a2e", corner_radius=8)
        status_frame.pack(fill="x", padx=10, pady=(0, 12))
        
        status_label = ctk.CTkLabel(
            status_frame,
            text="Estado Actual:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        status_label.pack(anchor="w", padx=15, pady=(10, 5))
        
        self.status_text = ctk.CTkTextbox(
            status_frame,
            height=90,
            font=ctk.CTkFont(size=12),
            fg_color="#0f3460"
        )
        self.status_text.pack(fill="x", padx=15, pady=(0, 10))
        
        buttons_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=10)
        
        self.install_btn = ctk.CTkButton(
            buttons_frame,
            text="📥 Descargar e Instalar Ollama",
            command=self.install_ollama_click,
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#00d9ff",
            hover_color="#0098d9"
        )
        self.install_btn.pack(fill="x", pady=5)

        # Iniciar / Cerrar siempre visibles, uno al lado del otro
        control_row = ctk.CTkFrame(buttons_frame, fg_color="transparent")
        control_row.pack(fill="x", pady=8)
        control_row.grid_columnconfigure(0, weight=1)
        control_row.grid_columnconfigure(1, weight=1)

        self.start_btn = ctk.CTkButton(
            control_row,
            text="▶️ Iniciar Ollama",
            command=self.start_ollama_click,
            height=48,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2ecc71",
            hover_color="#27ae60",
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            control_row,
            text="⏹️ Cerrar Ollama",
            command=self.stop_ollama_click,
            height=48,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#e94560",
            hover_color="#c7375f",
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ctk.CTkLabel(
            buttons_frame,
            text="Cerrar Ollama detiene todos sus procesos. Puedes volver a iniciarlo cuando quieras.",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        ).pack(pady=(0, 8))
        
        model_frame = ctk.CTkFrame(buttons_frame, fg_color="#16213e")
        model_frame.pack(fill="x", pady=10)
        
        model_label = ctk.CTkLabel(
            model_frame,
            text="Modelo recomendado:",
            font=ctk.CTkFont(size=12)
        )
        model_label.pack(pady=(10, 5))
        
        self.model_combo = ctk.CTkComboBox(
            model_frame,
            values=["llama3.2", "llama3.2:1b", "gemma2:2b", "phi3"],
            font=ctk.CTkFont(size=12),
            width=200
        )
        self.model_combo.set("llama3.2")
        self.model_combo.pack(pady=5)
        
        self.download_model_btn = ctk.CTkButton(
            model_frame,
            text="⬇️ Descargar Modelo",
            command=self.download_model_click,
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.download_model_btn.pack(pady=(5, 10))
        
        self.refresh_btn = ctk.CTkButton(
            buttons_frame,
            text="🔄 Actualizar Estado",
            command=self.update_status,
            height=35,
            fg_color="gray40",
            hover_color="gray30"
        )
        self.refresh_btn.pack(fill="x", pady=5)
        
        self.close_btn = ctk.CTkButton(
            buttons_frame,
            text="Cerrar esta ventana",
            command=self.destroy,
            height=35,
            fg_color="gray30",
            hover_color="gray25"
        )
        self.close_btn.pack(fill="x", pady=(10, 16))
        
    def update_status(self):
        self.status_text.delete("1.0", "end")
        
        is_installed = self.installer.is_ollama_installed()
        is_running = self.installer.is_ollama_running()
        models = self.installer.get_installed_models()
        
        if is_installed:
            self.status_text.insert("end", "✅ Ollama está instalado\n")
            self.install_btn.configure(state="disabled", text="✅ Ollama ya instalado")
        else:
            self.status_text.insert("end", "❌ Ollama NO está instalado\n")
            self.install_btn.configure(state="normal", text="📥 Descargar e Instalar Ollama")
            
        if is_running:
            self.status_text.insert("end", "✅ Servicio Ollama está ejecutándose\n")
            self.start_btn.configure(state="disabled", text="✅ Ollama en marcha")
            self.stop_btn.configure(state="normal", text="⏹️ Cerrar Ollama")
        else:
            self.status_text.insert("end", "❌ Servicio Ollama NO está ejecutándose\n")
            self.start_btn.configure(
                state="normal" if is_installed else "disabled",
                text="▶️ Iniciar Ollama",
            )
            # Siempre visible; se puede pulsar para forzar cierre por si quedó un proceso colgado
            self.stop_btn.configure(state="normal", text="⏹️ Cerrar Ollama")
            
        if models:
            self.status_text.insert("end", f"\n📦 Modelos instalados ({len(models)}):\n")
            for model in models:
                self.status_text.insert("end", f"  • {model}\n")
        else:
            self.status_text.insert("end", "\n❌ No hay modelos instalados\n")
            
        self.download_model_btn.configure(
            state="normal" if (is_installed and is_running) else "disabled"
        )
        
    def install_ollama_click(self):
        response = messagebox.askyesno(
            "Confirmar Instalación",
            "Se descargará e instalará Ollama desde ollama.com\n\n"
            "El instalador se ejecutará automáticamente.\n"
            "¿Deseas continuar?"
        )
        
        if not response:
            return
            
        self.install_btn.configure(state="disabled", text="⏳ Descargando...")
        
        def install_thread():
            try:
                installer_path = self.installer.download_ollama_installer(
                    lambda msg: self.after(0, lambda: self.status_text.insert("end", f"{msg}\n"))
                )
                
                self.after(0, lambda: messagebox.showinfo(
                    "Instalador Descargado",
                    "El instalador de Ollama se ejecutará ahora.\n"
                    "Sigue las instrucciones en pantalla.\n\n"
                    "Cuando termine, haz clic en 'Actualizar Estado'."
                ))
                
                self.installer.install_ollama(installer_path)
                
                self.after(0, lambda: self.update_status())
                
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.after(0, lambda: self.install_btn.configure(state="normal", text="📥 Descargar e Instalar Ollama"))
                
        threading.Thread(target=install_thread, daemon=True).start()
        
    def start_ollama_click(self):
        try:
            self.installer.start_ollama_service()
            self.status_text.insert("end", "\n⏳ Iniciando Ollama...\n")
            
            self.after(2000, self.update_status)
            
            messagebox.showinfo(
                "Servicio Iniciado",
                "Ollama se está iniciando en segundo plano.\n"
                "Espera unos segundos y actualiza el estado."
            )
            
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def stop_ollama_click(self):
        confirm = messagebox.askyesno(
            "Cerrar Ollama",
            "Se cerrarán todos los procesos de Ollama (app y servidor).\n"
            "Podrás volver a iniciarlo cuando lo necesites.\n\n"
            "¿Continuar?",
        )
        if not confirm:
            return

        try:
            result = self.installer.stop_ollama_processes()
            killed = result.get("killed", [])
            errors = result.get("errors", [])

            if killed:
                self.status_text.insert(
                    "end",
                    f"\n⏹️ Procesos cerrados: {', '.join(killed)}\n",
                )
                messagebox.showinfo(
                    "Ollama cerrado",
                    "Los procesos de Ollama se cerraron correctamente.\n"
                    "Usa 'Iniciar Servicio' cuando los necesites de nuevo.",
                )
            else:
                # Puede que ya estuviera cerrado o que taskkill no encontrara procesos
                still_running = self.installer.is_ollama_running()
                if still_running:
                    messagebox.showwarning(
                        "Atención",
                        "No se pudieron cerrar todos los procesos.\n"
                        + ("\n".join(errors) if errors else "Intenta cerrar Ollama desde la bandeja del sistema."),
                    )
                else:
                    messagebox.showinfo(
                        "Ollama cerrado",
                        "Ollama ya no está ejecutándose.",
                    )

            self.after(500, self.update_status)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            
    def download_model_click(self):
        model_name = self.model_combo.get()
        
        response = messagebox.askyesno(
            "Confirmar Descarga",
            f"Se descargará el modelo '{model_name}'.\n"
            f"Esto puede tardar varios minutos dependiendo de tu conexión.\n\n"
            f"¿Deseas continuar?"
        )
        
        if not response:
            return
            
        self.download_model_btn.configure(state="disabled", text="⏳ Descargando...")
        self.status_text.insert("end", f"\n⏳ Descargando modelo {model_name}...\n")
        
        def download_thread():
            try:
                self.installer.pull_model(
                    model_name,
                    lambda msg: self.after(0, lambda: self.status_text.insert("end", f"{msg}\n"))
                )
                
                self.after(0, lambda: messagebox.showinfo(
                    "Descarga Completa",
                    f"El modelo '{model_name}' se descargó correctamente.\n"
                    f"Ya puedes usar el asistente."
                ))
                
                self.after(0, lambda: self.update_status())
                
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.download_model_btn.configure(
                    state="normal",
                    text="⬇️ Descargar Modelo"
                ))
                
        threading.Thread(target=download_thread, daemon=True).start()
