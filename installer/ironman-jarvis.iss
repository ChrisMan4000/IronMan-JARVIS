; Inno Setup recipe (https://jrsoftware.org/isinfo.php) for the optional Windows installer.
; Build: download the repo ZIP, unzip it, open this file in Inno Setup, press Compile.
; It packs the repo (not .git, not this folder). The questions are asked on wizard pages in HUD colors (each with a "learn more" link),
; then install-jarvis.ps1 runs hidden with -FromWizard and the answers as parameters; the wizard shows its progress lines.
; The installer is NOT code-signed, so Windows SmartScreen will warn ("More info" > "Run anyway").
; Works with Inno Setup 6 (no callbacks used). Colors in the code are BGR: $FFD319 = HUD cyan #19d3ff, $3D9AFF = HUD orange #ff9a3d.
[Setup]
AppName=IronMan J.A.R.V.I.S.
AppVersion=1.1
AppPublisher=ChrisMan4000
AppPublisherURL=https://github.com/ChrisMan4000/IronMan-JARVIS
DefaultDirName={localappdata}\IronMan-JARVIS
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..
OutputBaseFilename=IronMan-JARVIS-Installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardResizable=yes
WizardImageFile=wizard-side.bmp,wizard-side-150.bmp,wizard-side-200.bmp
WizardSmallImageFile=wizard-small.bmp,wizard-small-200.bmp
SetupIconFile=..\assets\jarvis.ico
UninstallDisplayIcon={app}\assets\jarvis.ico

[Messages]
WelcomeLabel1=IronMan J.A.R.V.I.S.
WelcomeLabel2=A private AI assistant with a full-screen HUD. The AI runs on your own PC (LM Studio), nothing is sent to a cloud AI.%n%nOn the next pages you choose the optional parts. Each one has a link where you can read more first.%n%nBased on OpenJarvis (https://github.com/open-jarvis/OpenJarvis, Apache-2.0). Vibecoded with the free version of Claude. Not yet tested on a freshly wiped PC.
FinishedHeadingLabel=Setup finished

[Files]
Source: "..\*"; DestDir: "{app}"; Excludes: "installer\*,.git\*,IronMan-JARVIS-Installer.exe"; Flags: recursesubdirs createallsubdirs
Source: "list-llms.ps1"; Flags: dontcopy
Source: "..\tools\jarvis-common.ps1"; Flags: dontcopy
Source: "..\tools\voice-rec.ps1"; Flags: dontcopy
Source: "..\tools\model-search.ps1"; Flags: dontcopy

[UninstallDelete]
; the setup script creates the Python environment, node_modules, caches and logs inside the folder: remove all of it
Type: filesandordirs; Name: "{app}"

[Code]
const
  CBg     = $18120B;   { #0b1218 }
  CCyan   = $FFD319;   { #19d3ff }
  COrange = $3D9AFF;   { #ff9a3d }
  CText   = $F5E9BF;   { #bfe9f5 }
  K1Text  = 'Kokoro   (one size only, 82 million parameters; light, runs on any PC, about 0.3 GB)';
  K2Text  = 'Chatterbox   (more natural, can copy a voice; NVIDIA graphics card, about 4 GB graphics memory, several GB download)';

function DwmSetWindowAttribute(hwnd: HWND; dwAttribute: DWORD; var pvAttribute: DWORD; cbAttribute: DWORD): Longint;
  external 'DwmSetWindowAttribute@dwmapi.dll stdcall delayload';

function SetEnvironmentVariableW(lpName, lpValue: String): LongWord;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ small message pump so the wizard window stays responsive while the script runs }
type
  TMsg = record
    hwnd: LongWord; message: LongWord; wParam: Longint; lParam: Longint; time: LongWord; ptx: Longint; pty: Longint;
  end;
function PeekMessageW(var lpMsg: TMsg; hWnd: LongWord; wMsgFilterMin, wMsgFilterMax, wRemoveMsg: LongWord): Longint;
  external 'PeekMessageW@user32.dll stdcall';
function TranslateMessage(var lpMsg: TMsg): Longint;
  external 'TranslateMessage@user32.dll stdcall';
function DispatchMessageW(var lpMsg: TMsg): Longint;
  external 'DispatchMessageW@user32.dll stdcall';

procedure PumpMessages;
var Msg: TMsg;
begin
  while PeekMessageW(Msg, 0, 0, 0, 1) <> 0 do
  begin
    TranslateMessage(Msg);
    DispatchMessageW(Msg);
  end;
end;

var
  HuePage, TadoPage, SonosPage, WakePage, ModelPage, VoicePage, TtsPage, RagPage, KeyPage, CityPage: TWizardPage;
  HueCheck, TadoCheck, SonosCheck, WakeCheck, RagCheck, VoiceCheck: TNewCheckBox;
  HueIpEdit, SonosIpEdit, KeyEdit, CityEdit: TNewEdit;
  RbExist, RbT1, RbT2, RbT3, RbSkip, VoiceRbKokoro, VoiceRbChatterbox: TNewRadioButton;
  ModelCombo, WhisperCombo: TNewComboBox;
  ClipEdit: TNewEdit;
  ClipHint, ModelTip: TNewStaticText;
  OnlinePage: TWizardPage;
  OnlineBtn: TNewButton;
  OnlineInfo: TNewStaticText;
  RbOnYes, RbOnNo: TNewRadioButton;
  OnlineRepo, OnlineGB: String;
  ModelGBs: TArrayOfString;
  VoiceRecKey, RecWhisper, RecTts: String;
  HasNvidia: Boolean;
  ModelInfo, VoiceInfo: TNewStaticText;
  ModelKeys: TArrayOfString;
  { filled from the helper scripts' output, so the lists live only in tools\jarvis-common.ps1:
    TIER lines of list-llms.ps1 (index 1-3) and WOPT lines of voice-rec.ps1 (index 0-4) }
  TierIds, TierKeys, TierGbs, TierTexts: TArrayOfString;
  WhisperIds, WhisperTexts: TArrayOfString;
  Lbls: array of TNewStaticText;
  CheckList: array of TNewCheckBox;
  RadioList: array of TNewRadioButton;
  LmFound: Boolean;
  ModelsDetected: Boolean;
  StatusPath: String;
  SetupCode: Integer;

{ ---------- small helpers ---------- }

function NextField(var S: String): String;
var P: Integer;
begin
  P := Pos('|', S);
  if P = 0 then begin Result := S; S := ''; end
  else begin Result := Copy(S, 1, P - 1); Delete(S, 1, P); end;
end;

function ValidIp(const S: String): Boolean;
var I, Dots, SegLen, Cur: Integer; C: Char;
begin
  Result := False; Dots := 0; SegLen := 0; Cur := 0;
  for I := 1 to Length(S) do
  begin
    C := S[I];
    if (C >= '0') and (C <= '9') then
    begin
      Cur := Cur * 10 + (Ord(C) - 48); SegLen := SegLen + 1;
      if (SegLen > 3) or (Cur > 255) then Exit;
    end
    else if C = '.' then
    begin
      if SegLen = 0 then Exit;
      Dots := Dots + 1; SegLen := 0; Cur := 0;
    end
    else Exit;
  end;
  Result := (Dots = 3) and (SegLen > 0);
end;

function ValidModelId(const S: String): Boolean;
var I: Integer; C: Char;
begin
  Result := Length(S) > 0;
  for I := 1 to Length(S) do
  begin
    C := S[I];
    if not (((C >= 'a') and (C <= 'z')) or ((C >= 'A') and (C <= 'Z')) or ((C >= '0') and (C <= '9')) or (Pos(String(C), '._:/@+-') > 0)) then
    begin Result := False; Exit; end;
  end;
end;

{ the LM Studio APP must exist; a leftover .lmstudio folder (models, lms.exe) from an uninstalled app does not count }
function LmStudioInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\LM Studio\LM Studio.exe')) or FileExists(ExpandConstant('{pf}\LM Studio\LM Studio.exe'));
end;

procedure LinkClick(Sender: TObject);
var ErrorCode: Integer;
begin
  ShellExec('open', TNewStaticText(Sender).Hint, '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
end;

function NewPage(AfterId: Integer; const Cap, Desc: String): TWizardPage;
begin
  Result := CreateCustomPage(AfterId, Cap, Desc);
  Result.Surface.Color := CBg;
end;

function AddText(Page: TWizardPage; var Y: Integer; const Txt: String; AColor: TColor; Bold: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := 0;
  Result.Top := Y;
  Result.Width := Page.SurfaceWidth;
  Result.AutoSize := True;
  Result.WordWrap := True;
  Result.Caption := Txt;
  Result.Font.Color := AColor;
  if Bold then Result.Font.Style := [fsBold];
  Y := Y + Result.Height + ScaleY(6);
end;

function AddLink(Page: TWizardPage; var Y: Integer; const Txt, Url: String): TNewStaticText;
begin
  Result := AddText(Page, Y, Txt + '  -  ' + Url, CCyan, False);
  Result.Font.Style := [fsUnderline];
  Result.Cursor := crHand;
  Result.Hint := Url;
  Result.OnClick := @LinkClick;
end;

procedure CheckLabelClick(Sender: TObject); forward;
procedure RadioLabelClick(Sender: TObject); forward;
procedure OnlineCheckClick(Sender: TObject); forward;
procedure WizardResize(Sender: TObject); forward;

{ Windows draws the text of check boxes and radio buttons itself and ignores the color, so the real control has no text
  and a colored label next to it carries the text (clicking the label works like clicking the box). }
function AddLabelFor(Page: TWizardPage; Y: Integer; const Txt: String; AColor: TColor): TNewStaticText;
var N: Integer;
begin
  Result := TNewStaticText.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := ScaleX(22);
  Result.Top := Y + ScaleY(2);
  Result.Width := Page.SurfaceWidth - ScaleX(22);
  Result.AutoSize := True;
  Result.WordWrap := True;
  Result.Caption := Txt;
  Result.Font.Color := AColor;
  Result.Cursor := crHand;
  N := GetArrayLength(Lbls);
  SetArrayLength(Lbls, N + 1);
  Lbls[N] := Result;
end;

function AddCheck(Page: TWizardPage; var Y: Integer; const Txt: String): TNewCheckBox;
var L: TNewStaticText; N: Integer;
begin
  Result := TNewCheckBox.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := 0;
  Result.Top := Y;
  Result.Width := ScaleX(18);
  Result.Height := ScaleY(20);
  Result.Caption := '';
  L := AddLabelFor(Page, Y, Txt, COrange);
  N := GetArrayLength(CheckList);
  SetArrayLength(CheckList, N + 1);
  CheckList[N] := Result;
  L.Tag := N;
  L.OnClick := @CheckLabelClick;
  Y := Y + ScaleY(26);
end;

{ the wizard is a 32-bit program: a plain powershell.exe would be the 32-bit one and cannot see nvidia-smi in System32 }
function PsExe: String;
begin
  Result := 'powershell.exe';
  if FileExists(ExpandConstant('{win}\Sysnative\WindowsPowerShell\v1.0\powershell.exe')) then
    Result := ExpandConstant('{win}\Sysnative\WindowsPowerShell\v1.0\powershell.exe');
end;

function AddRadio(Page: TWizardPage; var Y: Integer; const Txt: String): TNewRadioButton;
var L: TNewStaticText; N: Integer;
begin
  Result := TNewRadioButton.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := 0;
  Result.Top := Y;
  Result.Width := ScaleX(18);
  Result.Height := ScaleY(20);
  Result.Caption := '';
  L := AddLabelFor(Page, Y, Txt, CText);
  N := GetArrayLength(RadioList);
  SetArrayLength(RadioList, N + 1);
  RadioList[N] := Result;
  L.Tag := N;
  Result.Tag := GetArrayLength(Lbls) - 1;   { index of this radio's label }
  L.OnClick := @RadioLabelClick;
  Y := Y + L.Height + ScaleY(6);
  if L.Height < ScaleY(30) then Y := Y + ScaleY(15);   { a one-line label can wrap when the mark is added }
end;

procedure SetRadioText(R: TNewRadioButton; const Txt: String);
begin
  Lbls[R.Tag].Caption := Txt;
end;

procedure SetRadioLook(R: TNewRadioButton);
begin
  if R.Enabled then Lbls[R.Tag].Font.Color := CText else Lbls[R.Tag].Font.Color := $707070;
end;

{ Windows 11: title bar and window border in the HUD background color (older Windows keeps its normal frame) }
procedure ThemeFrame(Wnd: HWND);
var V: DWORD;
begin
  try
    V := 1; DwmSetWindowAttribute(Wnd, 20, V, 4);       { dark mode frame }
    V := CBg; DwmSetWindowAttribute(Wnd, 35, V, 4);     { title bar color }
    V := CBg; DwmSetWindowAttribute(Wnd, 34, V, 4);     { border color }
    V := CCyan; DwmSetWindowAttribute(Wnd, 36, V, 4);   { title text color }
  except
  end;
end;

procedure ThemeWizard;
begin
  ThemeFrame(WizardForm.Handle);
  WizardForm.Color := CBg;
  WizardForm.MainPanel.Color := CBg;
  WizardForm.InnerPage.Color := CBg;
  WizardForm.WelcomePage.Color := CBg;
  WizardForm.FinishedPage.Color := CBg;
  WizardForm.SelectDirPage.Color := CBg;
  WizardForm.ReadyPage.Color := CBg;
  WizardForm.InstallingPage.Color := CBg;
  WizardForm.PageNameLabel.Font.Color := CCyan;
  WizardForm.PageDescriptionLabel.Font.Color := CText;
  WizardForm.WelcomeLabel1.Font.Color := CCyan;
  WizardForm.WelcomeLabel2.Font.Color := CText;
  WizardForm.FinishedHeadingLabel.Font.Color := CCyan;
  WizardForm.FinishedLabel.Font.Color := CText;
  WizardForm.SelectDirLabel.Font.Color := CText;
  WizardForm.SelectDirBrowseLabel.Font.Color := CText;
  WizardForm.ReadyLabel.Font.Color := CText;
  WizardForm.StatusLabel.Font.Color := COrange;
  WizardForm.FilenameLabel.Font.Color := CText;
end;

procedure HueClick(Sender: TObject);
begin
  HueIpEdit.Enabled := HueCheck.Checked;
end;

procedure SonosClick(Sender: TObject);
begin
  SonosIpEdit.Enabled := SonosCheck.Checked;
end;

procedure ModelRadioClick(Sender: TObject);
begin
  ModelCombo.Enabled := RbExist.Checked and RbExist.Enabled;
  ClipEdit.Enabled := VoiceRbChatterbox.Checked and VoiceRbChatterbox.Enabled;
end;

procedure CheckLabelClick(Sender: TObject);
var C: TNewCheckBox;
begin
  C := CheckList[TNewStaticText(Sender).Tag];
  C.Checked := not C.Checked;
  HueClick(nil);
  SonosClick(nil);
end;

procedure RadioLabelClick(Sender: TObject);
var R: TNewRadioButton;
begin
  R := RadioList[TNewStaticText(Sender).Tag];
  if R.Enabled then
  begin
    R.Checked := True;
    ModelRadioClick(nil);
  end;
end;

{ Whisper size of a combo box entry (the list comes from tools\voice-rec.ps1; 'base' when it could not be read) }
function WhisperId(I: Integer): String;
begin
  if (I >= 0) and (I < GetArrayLength(WhisperIds)) then Result := WhisperIds[I] else Result := 'base';
end;

{ ---------- pages ---------- }

procedure InitializeWizard;
var Y: Integer; Saved: String; Ip8: AnsiString;
begin
  ThemeWizard;
  WizardForm.BorderStyle := bsSizeable;   { make sure the window frame can be dragged and maximized }
  WizardForm.BorderIcons := [biSystemMenu, biMinimize, biMaximize];
  WizardForm.OnResize := @WizardResize;   { the window can be resized: keep the page content centered }
  WizardForm.WizardSmallBitmapImage.Left := WizardForm.WizardSmallBitmapImage.Left - ScaleX(14);   { logo a bit more to the left }
  WizardForm.PageNameLabel.Width := WizardForm.WizardSmallBitmapImage.Left - WizardForm.PageNameLabel.Left - ScaleX(8);   { the texts must not cover the logo }
  WizardForm.PageDescriptionLabel.Width := WizardForm.WizardSmallBitmapImage.Left - WizardForm.PageDescriptionLabel.Left - ScaleX(8);
  StatusPath := ExpandConstant('{tmp}\jarvis-status.txt');
  ModelsDetected := False;
  SetupCode := 0;

  { Philips Hue }
  HuePage := NewPage(wpSelectDir, 'Philips Hue Smart Lights (optional)', 'Switch your lights on and off by voice or text.');
  Y := 0;
  AddText(HuePage, Y, 'Lets Jarvis switch your Philips Hue lights on and off ("turn off the kitchen lights"). Every change is read back from the bridge. Needs a Hue bridge in your home network.', CText, False);
  AddLink(HuePage, Y, 'Philips Hue Smart Lights', 'https://www.philips-hue.com/en-us/explore-hue');
  HueCheck := AddCheck(HuePage, Y, 'Use Philips Hue Smart Lights');
  HueCheck.OnClick := @HueClick;
  AddText(HuePage, Y, 'IP address of your Hue bridge (Hue app > Settings > Bridge):', CText, False);
  HueIpEdit := TNewEdit.Create(HuePage);
  HueIpEdit.Parent := HuePage.Surface;
  HueIpEdit.Left := 0; HueIpEdit.Top := Y; HueIpEdit.Width := ScaleX(160);
  HueIpEdit.Enabled := False;
  Y := Y + ScaleY(30);
  AddText(HuePage, Y, 'When the installation starts, a message asks you to press the round button on top of the bridge.', COrange, False);

  { Tado }
  TadoPage := NewPage(HuePage.ID, 'Tado Smart Heating (optional)', 'Control your Tado radiator valves.');
  Y := 0;
  AddText(TadoPage, Y, 'Lets Jarvis set or switch off your Tado heating ("heating off in the living room"). Needs a Tado account. Your browser opens once later: sign in to your Tado account there first (the confirm button does nothing before that), then approve the login within 5 minutes.', CText, False);
  AddLink(TadoPage, Y, 'Tado Smart Heating', 'https://www.tado.com/en');
  TadoCheck := AddCheck(TadoPage, Y, 'Use Tado Smart Heating');

  { Sonos }
  SonosPage := NewPage(TadoPage.ID, 'Sonos speaker or soundbar (optional)', 'Play, pause and change the volume by voice or text.');
  Y := 0;
  AddText(SonosPage, Y, 'Lets Jarvis play, pause, skip, mute and set the volume of one Sonos speaker or soundbar ("turn the sound bar down"). It talks to the speaker directly inside your home network: no account, no cloud. Every change is read back, and the volume is capped at 80 percent.', CText, False);
  AddLink(SonosPage, Y, 'Sonos', 'https://www.sonos.com');
  SonosCheck := AddCheck(SonosPage, Y, 'Use a Sonos speaker or soundbar');
  SonosCheck.OnClick := @SonosClick;
  AddText(SonosPage, Y, 'IP address of the speaker (Sonos app > Settings > System > About My System):', CText, False);
  SonosIpEdit := TNewEdit.Create(SonosPage);
  SonosIpEdit.Parent := SonosPage.Surface;
  SonosIpEdit.Left := 0; SonosIpEdit.Top := Y; SonosIpEdit.Width := ScaleX(160);
  SonosIpEdit.Enabled := False;
  Y := Y + ScaleY(30);
  AddText(SonosPage, Y, 'Tip: give the speaker a fixed address in your router so it does not change.', CText, False);

  { wake word }
  WakePage := NewPage(SonosPage.ID, 'Wake word (optional)', 'Say "Hey Jarvis" to start talking.');
  Y := 0;
  AddText(WakePage, Y, 'Listens for "Hey Jarvis" with the open-source openWakeWord. It needs its own Python environment and a few hundred MB, a few minutes of setup. Without it you click the ring or press F6.', CText, False);
  AddLink(WakePage, Y, 'openWakeWord', 'https://github.com/dscripka/openWakeWord');
  WakeCheck := AddCheck(WakePage, Y, 'Set up the wake word "Hey Jarvis"');
  WakeCheck.Checked := True;   { on by default }

  { language model }
  ModelPage := NewPage(WakePage.ID, 'Language model', 'The AI that answers you. It runs in LM Studio on your PC.');
  Y := 0;
  AddLink(ModelPage, Y, 'LM Studio', 'https://lmstudio.ai');
  ModelInfo := AddText(ModelPage, Y, 'Looking at your PC...' + #13#10 + ' ', COrange, False);
  RbExist := AddRadio(ModelPage, Y, 'Use a model that is already in LM Studio:');
  ModelCombo := TNewComboBox.Create(ModelPage);
  ModelCombo.Parent := ModelPage.Surface;
  ModelCombo.Left := ScaleX(18); ModelCombo.Top := Y; ModelCombo.Width := ModelPage.SurfaceWidth - ScaleX(18);
  ModelCombo.Style := csDropDownList;
  ModelCombo.Enabled := False;
  Y := Y + ScaleY(28);
  { the texts are filled in by DetectModels from the TIER lines of list-llms.ps1 }
  RbT1 := AddRadio(ModelPage, Y, 'Small language model');
  RbT2 := AddRadio(ModelPage, Y, 'Medium language model');
  RbT3 := AddRadio(ModelPage, Y, 'Large language model');
  RbSkip := AddRadio(ModelPage, Y, 'Skip (I will download a model in LM Studio myself)');
  ModelTip := AddText(ModelPage, Y, 'Tip: the next step can search online for the newest models, if you like.', CText, False);
  ModelTip.Font.Style := [fsItalic];
  RbExist.Enabled := False;
  SetRadioLook(RbExist);
  RbT1.Checked := True;
  RbExist.OnClick := @ModelRadioClick; RbT1.OnClick := @ModelRadioClick; RbT2.OnClick := @ModelRadioClick;
  RbT3.OnClick := @ModelRadioClick; RbSkip.OnClick := @ModelRadioClick;

  { speech recognition (Whisper size) }
  { optional: look online for a newer model that fits the PC }
  OnlinePage := NewPage(ModelPage.ID, 'Newest models (optional)', 'Look online for a newer language model that fits your PC.');
  Y := 0;
  AddText(OnlinePage, Y, 'The three sizes on the previous page are a fixed list. This optional step asks Hugging Face for the newest chat models of the LM Studio community and suggests the biggest one that fits your PC. After the download the setup tests that the model can call tools (Jarvis needs that). If the test fails, your choice from the previous page is installed instead. You can skip this step.', CText, False);
  AddLink(OnlinePage, Y, 'Hugging Face: lmstudio-community', 'https://huggingface.co/lmstudio-community');
  OnlineBtn := TNewButton.Create(OnlinePage);
  OnlineBtn.Parent := OnlinePage.Surface;
  OnlineBtn.Left := 0; OnlineBtn.Top := Y; OnlineBtn.Width := ScaleX(200); OnlineBtn.Height := ScaleY(26);
  OnlineBtn.Caption := 'Check online now';
  OnlineBtn.OnClick := @OnlineCheckClick;
  Y := Y + ScaleY(36);
  OnlineInfo := AddText(OnlinePage, Y, 'Not checked yet.', COrange, False);
  Y := Y - OnlineInfo.Height - ScaleY(6);
  OnlineInfo.AutoSize := False; OnlineInfo.Height := ScaleY(48);
  Y := Y + ScaleY(54);
  RbOnYes := AddRadio(OnlinePage, Y, 'Use the model found online');
  RbOnNo := AddRadio(OnlinePage, Y, 'No, keep my choice from the previous page');
  RbOnYes.Enabled := False; SetRadioLook(RbOnYes);
  RbOnNo.Checked := True;

  VoicePage := NewPage(OnlinePage.ID, 'Speech recognition', 'How Jarvis understands what you say.');
  Y := 0;
  AddText(VoicePage, Y, 'Whisper (run through faster-whisper) turns your voice into text. A bigger size understands better but needs more download and memory. The size that fits your PC best is marked.', CText, False);
  AddLink(VoicePage, Y, 'faster-whisper', 'https://github.com/SYSTRAN/faster-whisper');
  AddLink(VoicePage, Y, 'Whisper sizes compared', 'https://github.com/openai/whisper#available-models-and-languages');
  VoiceInfo := AddText(VoicePage, Y, 'Looking at your PC...' + #13#10 + ' ', COrange, False);
  WhisperCombo := TNewComboBox.Create(VoicePage);
  WhisperCombo.Parent := VoicePage.Surface;
  WhisperCombo.Left := 0; WhisperCombo.Top := Y; WhisperCombo.Width := VoicePage.SurfaceWidth;
  WhisperCombo.Style := csDropDownList;
  Y := Y + ScaleY(28);

  { voice for the answers (Kokoro or Chatterbox) }
  TtsPage := NewPage(VoicePage.ID, 'Voice', 'How Jarvis sounds when it answers.');
  Y := 0;
  AddText(TtsPage, Y, 'Kokoro is small and works on every PC. Chatterbox sounds more natural and can copy a voice from a short clip, but it needs an NVIDIA graphics card and a long download. The best choice for your PC is marked.', CText, False);
  AddLink(TtsPage, Y, 'Kokoro', 'https://huggingface.co/hexgrad/Kokoro-82M');
  AddLink(TtsPage, Y, 'Chatterbox', 'https://github.com/resemble-ai/chatterbox');
  VoiceRbKokoro := AddRadio(TtsPage, Y, K1Text);
  VoiceRbChatterbox := AddRadio(TtsPage, Y, K2Text);
  VoiceRbKokoro.Checked := True;
  VoiceRbKokoro.OnClick := @ModelRadioClick; VoiceRbChatterbox.OnClick := @ModelRadioClick;
  ClipHint := AddText(TtsPage, Y, 'Optional, Chatterbox only: full path of a clear .wav, .mp3 or .flac clip (10-20 seconds, one speaker) of YOUR OWN voice, or a voice you have permission to copy. Empty = the built-in voice.', CText, False);
  Y := Y - ClipHint.Height - ScaleY(6);   { redo the layout: indented like the Chatterbox text, italic }
  ClipHint.Left := ScaleX(22); ClipHint.Width := TtsPage.SurfaceWidth - ScaleX(22);
  ClipHint.Font.Style := [fsItalic];
  Y := Y + ClipHint.Height + ScaleY(6);
  ClipEdit := TNewEdit.Create(TtsPage);
  ClipEdit.Parent := TtsPage.Surface;
  ClipEdit.Left := ScaleX(22); ClipEdit.Top := Y; ClipEdit.Width := TtsPage.SurfaceWidth - ScaleX(22);
  ClipEdit.Enabled := False;
  Y := Y + ScaleY(30);

  { document search }
  RagPage := NewPage(TtsPage.ID, 'Document search (optional)', 'Ask questions about your own PDF, Word and text files.');
  Y := 0;
  AddText(RagPage, Y, 'Uses the LM Studio plugin Big RAG to index your files. Indexing thousands of files takes hours and the feature is fussy. You finish its setup inside LM Studio afterwards.', CText, False);
  AddLink(RagPage, Y, 'Big RAG plugin', 'https://lmstudio.ai/mindstudio/big-rag');
  RagCheck := AddCheck(RagPage, Y, 'Set up document search');
  AddText(RagPage, Y, 'If LM Studio asks, click install for Big RAG there; the setup waits up to 2 minutes for it.', COrange, False);

  { web search key }
  KeyPage := NewPage(RagPage.ID, 'Web search (optional)', 'Lets Jarvis look things up on the internet.');
  Y := 0;
  AddText(KeyPage, Y, 'Web search uses the Firecrawl Web Data API and needs your own API key (it has a free plan with limited credits). Your search words are sent to Firecrawl. Leave the box empty to skip.', CText, False);
  AddLink(KeyPage, Y, 'Firecrawl Web Data API', 'https://www.firecrawl.dev/');
  AddText(KeyPage, Y, 'Your Firecrawl API key:', CText, False);
  KeyEdit := TNewEdit.Create(KeyPage);
  KeyEdit.Parent := KeyPage.Surface;
  KeyEdit.Left := 0; KeyEdit.Top := Y; KeyEdit.Width := KeyPage.SurfaceWidth;
  KeyEdit.PasswordChar := '*';
  Y := Y + ScaleY(30);
  AddText(KeyPage, Y, 'The key is stored as a Windows user environment variable on this PC only, never in a file in the project.', CText, False);
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'FIRECRAWL_API_KEY', Saved) and (Saved <> '') then
    AddText(KeyPage, Y, 'A key is already saved on this PC. Leave the box empty to keep it.', COrange, False);

  { home city: ATMOSPHERICS weather and the world-map home point (tools\set-home-city.ps1 writes frontend\public\hud-home.js) }
  CityPage := NewPage(KeyPage.ID, 'Your city', 'For the weather and the home point on the world map in the HUD.');
  Y := 0;
  AddText(CityPage, Y, 'Type the city you live in. The setup looks it up with the free Open-Meteo service (only the city name is sent). Leave the box empty to skip: the HUD then shows London, or keeps the city of an earlier install.', CText, False);
  AddLink(CityPage, Y, 'Open-Meteo geocoding', 'https://open-meteo.com/en/docs/geocoding-api');
  AddText(CityPage, Y, 'Your city:', CText, False);
  CityEdit := TNewEdit.Create(CityPage);
  CityEdit.Parent := CityPage.Surface;
  CityEdit.Left := 0; CityEdit.Top := Y; CityEdit.Width := CityPage.SurfaceWidth;
  Y := Y + ScaleY(30);
  AddText(CityPage, Y, 'Change it later with tools\set-home-city.ps1 in the install folder.', CText, False);

  { an earlier install left its settings (kept at uninstall): pre-fill the answers }
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'HUE_BRIDGE_IP', Saved) then Saved := '';
  if (Saved = '') and LoadStringFromFile(ExpandConstant('{%USERPROFILE}\.openjarvis\hue-ip.txt'), Ip8) then Saved := Trim(String(Ip8));
  if ValidIp(Saved) and FileExists(ExpandConstant('{%USERPROFILE}\.openjarvis\hue-key.txt')) then
  begin
    HueCheck.Checked := True;
    HueIpEdit.Text := Saved;
    HueIpEdit.Enabled := True;
  end;
  if FileExists(ExpandConstant('{%USERPROFILE}\.openjarvis\tado-token.json')) then TadoCheck.Checked := True;
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'SONOS_IP', Saved) then
    if ValidIp(Saved) then
    begin
      SonosCheck.Checked := True;
      SonosIpEdit.Text := Saved;
      SonosIpEdit.Enabled := True;
    end;
end;

procedure DetectModels;
var Lines: TArrayOfString; I, N, T, Rc, Tier, RecIdx: Integer; L, F, Gpu, Ram, Tmp, Mark, M, RecId: String;
begin
  ModelsDetected := True;
  RecIdx := -1; RecId := '';
  Tier := 1; Gpu := '0'; Ram := '?';
  Tmp := ExpandConstant('{tmp}\llms.txt');
  SetArrayLength(TierIds, 4); SetArrayLength(TierKeys, 4); SetArrayLength(TierGbs, 4); SetArrayLength(TierTexts, 4);
  ExtractTemporaryFile('jarvis-common.ps1');
  ExtractTemporaryFile('list-llms.ps1');
  Exec(PsExe, '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{tmp}\list-llms.ps1') + '" -Out "' + Tmp + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc);
  if LoadStringsFromFile(Tmp, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      L := Trim(Lines[I]);
      if Pos('REC|', L) = 1 then
      begin
        Delete(L, 1, 4);
        Tier := StrToIntDef(NextField(L), 1);
        Gpu := NextField(L);
        Ram := NextField(L);
      end
      else if Pos('TIER|', L) = 1 then
      begin
        Delete(L, 1, 5);
        T := StrToIntDef(NextField(L), 0);
        if (T >= 1) and (T <= 3) then
        begin
          TierIds[T] := NextField(L);
          TierKeys[T] := NextField(L);
          TierGbs[T] := NextField(L);
          TierTexts[T] := 'About ' + TierGbs[T] + ' GB   ' + TierIds[T] + '   (' + L + ')';
        end;
      end
      else if Pos('MODEL|', L) = 1 then
      begin
        Delete(L, 1, 6);
        if (RecId = '') and (Tier >= 1) and (Tier <= 3) then RecId := TierKeys[Tier];
        F := NextField(L);
        if ValidModelId(F) then
        begin
          N := GetArrayLength(ModelKeys);
          SetArrayLength(ModelKeys, N + 1);
          ModelKeys[N] := F;
          SetArrayLength(ModelGBs, N + 1);
          ModelGBs[N] := L;
          if (F = RecId) or ((Tier = 1) and (Pos(RecId, LowerCase(F)) > 0) and (Pos('uncensored', LowerCase(F)) = 0)) then begin RecIdx := N; ModelCombo.Items.Add(F + '  (' + L + ' GB)   <-- recommended'); end
          else ModelCombo.Items.Add(F + '  (' + L + ' GB)');
        end;
      end;
    end;
  LmFound := LmStudioInstalled;
  if LmFound then M := 'LM Studio: found on this PC.' else M := 'LM Studio: not found. The setup installs it for you (winget).';
  ModelInfo.Caption := M + #13#10 + 'Your PC: GPU memory ' + Gpu + ' GB, RAM ' + Ram + ' GB. The recommended size is marked.';
  Mark := '   <-- recommended';
  for T := 1 to 3 do
    if TierTexts[T] <> '' then
    begin
      M := TierTexts[T];
      if T = Tier then M := M + Mark;
      if T = 1 then SetRadioText(RbT1, M) else if T = 2 then SetRadioText(RbT2, M) else SetRadioText(RbT3, M);
    end;
  if LmFound then M := 'LM Studio: found on this PC.' else M := 'LM Studio: not found. The setup installs it for you (winget).';
  RbT1.Checked := Tier = 1; RbT2.Checked := Tier = 2; RbT3.Checked := Tier = 3;
  if ModelCombo.Items.Count > 0 then
  begin
    RbExist.Enabled := True;
    SetRadioLook(RbExist);
    if RecIdx >= 0 then ModelCombo.ItemIndex := RecIdx else ModelCombo.ItemIndex := 0;
    RbExist.Checked := True;
    if RecIdx >= 0 then ModelInfo.Caption := M + #13#10 + 'Your PC: GPU memory ' + Gpu + ' GB, RAM ' + Ram + ' GB. The recommended model is already installed.';
  end;
  ModelRadioClick(nil);
end;

{ button on the optional page: asks Hugging Face (tools\model-search.ps1, read-only) for the best new model that fits }
procedure OnlineCheckClick(Sender: TObject);
var Lines: TArrayOfString; Tmp, L: String; Rc, I: Integer;
begin
  OnlineBtn.Enabled := False;
  OnlineInfo.Caption := 'Searching Hugging Face, please wait a few seconds...';
  WizardForm.Update;
  OnlineRepo := ''; OnlineGB := '';
  Tmp := ExpandConstant('{tmp}\models-online.txt');
  DeleteFile(Tmp);
  ExtractTemporaryFile('jarvis-common.ps1');
  ExtractTemporaryFile('model-search.ps1');
  Exec(PsExe, '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{tmp}\model-search.ps1') + '" -Out "' + Tmp + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc);
  if LoadStringsFromFile(Tmp, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      L := Trim(Lines[I]);
      if Pos('BEST|', L) = 1 then
      begin
        Delete(L, 1, 5);
        OnlineRepo := NextField(L);
        OnlineGB := NextField(L);
        if not ValidModelId(OnlineRepo) then OnlineRepo := '';
      end;
    end;
  if OnlineRepo <> '' then
  begin
    OnlineInfo.Caption := 'Found: ' + OnlineRepo + ' (about ' + OnlineGB + ' GB, estimated). It fits your PC.';
    SetRadioText(RbOnYes, 'Use ' + OnlineRepo + '   (about ' + OnlineGB + ' GB, found online)   <-- newest that fits');
    RbOnYes.Enabled := True; SetRadioLook(RbOnYes);
    RbOnYes.Checked := True;
  end
  else
  begin
    OnlineInfo.Caption := 'Nothing suitable found (or no internet). Your choice from the previous page stays.';
    RbOnYes.Enabled := False; SetRadioLook(RbOnYes);
    RbOnNo.Checked := True;
  end;
  VoiceRecKey := '';
  OnlineBtn.Enabled := True;
end;

{ looks at the PC (tools\voice-rec.ps1, read-only) and marks the best Whisper size and voice; runs again only when the language model choice changed }
procedure DetectVoice;
var Lines: TArrayOfString; I, N, Rc: Integer; L, Tmp, Gb, Vram, Ram, Nv, FreeGb, Mark, Dl, Gm: String;
begin
  Gb := '-1';
  if RbOnYes.Checked and (OnlineGB <> '') then Gb := OnlineGB
  else if RbExist.Checked and (ModelCombo.ItemIndex >= 0) then Gb := ModelGBs[ModelCombo.ItemIndex]
  else if RbT1.Checked and (TierGbs[1] <> '') then Gb := TierGbs[1]
  else if RbT2.Checked and (TierGbs[2] <> '') then Gb := TierGbs[2]
  else if RbT3.Checked and (TierGbs[3] <> '') then Gb := TierGbs[3];
  if Gb = VoiceRecKey then Exit;
  VoiceRecKey := Gb;
  Tmp := ExpandConstant('{tmp}\voicerec.txt');
  DeleteFile(Tmp);
  ExtractTemporaryFile('jarvis-common.ps1');
  ExtractTemporaryFile('voice-rec.ps1');
  Exec(PsExe, '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{tmp}\voice-rec.ps1') + '" -Out "' + Tmp + '" -LlmGB ' + Gb, '', SW_HIDE, ewWaitUntilTerminated, Rc);
  SetArrayLength(WhisperIds, 0); SetArrayLength(WhisperTexts, 0);
  RecWhisper := 'base'; RecTts := 'kokoro'; HasNvidia := False;
  Vram := '0'; Ram := '?'; Nv := '0'; FreeGb := '0';
  if LoadStringsFromFile(Tmp, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      L := Trim(Lines[I]);
      if Pos('HW|', L) = 1 then begin Delete(L, 1, 3); Vram := NextField(L); Ram := NextField(L); Nv := NextField(L); end
      else if Pos('WHISPER|', L) = 1 then RecWhisper := Copy(L, 9, 20)
      else if Pos('VOICE|', L) = 1 then RecTts := Copy(L, 7, 20)
      else if Pos('FREE|', L) = 1 then FreeGb := Copy(L, 6, 20)
      else if Pos('WOPT|', L) = 1 then
      begin
        Delete(L, 1, 5);
        N := GetArrayLength(WhisperIds);
        SetArrayLength(WhisperIds, N + 1); SetArrayLength(WhisperTexts, N + 1);
        WhisperIds[N] := NextField(L);
        Dl := NextField(L); Gm := NextField(L);
        WhisperTexts[N] := WhisperIds[N] + '   (about ' + Dl + ' GB download, about ' + Gm + ' GB graphics memory, ' + L + ')';
      end;
    end;
  HasNvidia := Nv = '1';
  if HasNvidia then
    VoiceInfo.Caption := 'Your PC: NVIDIA graphics card with ' + Vram + ' GB, RAM ' + Ram + ' GB. About ' + FreeGb + ' GB of graphics memory stay free next to the language model.'
  else
    VoiceInfo.Caption := 'Your PC: no NVIDIA graphics card found, RAM ' + Ram + ' GB. Speech recognition runs on the processor, so the smaller sizes are the sensible ones.';
  Mark := '   <-- recommended';
  WhisperCombo.Items.Clear;
  if GetArrayLength(WhisperIds) = 0 then
  begin
    { voice-rec.ps1 gave no list: offer the safe default only }
    SetArrayLength(WhisperIds, 1); SetArrayLength(WhisperTexts, 1);
    WhisperIds[0] := 'base'; WhisperTexts[0] := 'base   (the PC check did not answer; you can change the size later with tools\voice-setup.ps1 -Ask)';
  end;
  for I := 0 to GetArrayLength(WhisperIds) - 1 do
  begin
    if WhisperIds[I] = RecWhisper then WhisperCombo.Items.Add(WhisperTexts[I] + Mark)
    else WhisperCombo.Items.Add(WhisperTexts[I]);
    if WhisperIds[I] = RecWhisper then WhisperCombo.ItemIndex := I;
  end;
  if WhisperCombo.ItemIndex < 0 then WhisperCombo.ItemIndex := 0;
  SetRadioText(VoiceRbKokoro, K1Text);
  SetRadioText(VoiceRbChatterbox, K2Text);
  if RecTts = 'chatterbox' then SetRadioText(VoiceRbChatterbox, K2Text + Mark) else SetRadioText(VoiceRbKokoro, K1Text + Mark);
  VoiceRbChatterbox.Enabled := HasNvidia;
  SetRadioLook(VoiceRbChatterbox);
  if not HasNvidia then SetRadioText(VoiceRbChatterbox, K2Text + '   (not possible: no NVIDIA card found)');
  VoiceRbChatterbox.Checked := (RecTts = 'chatterbox') and HasNvidia;
  VoiceRbKokoro.Checked := not VoiceRbChatterbox.Checked;
  ModelRadioClick(nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = TtsPage.ID then
    if VoiceRbChatterbox.Checked and (Trim(ClipEdit.Text) <> '') and (not FileExists(Trim(ClipEdit.Text))) then
    begin
      MsgBox('The voice clip was not found. Check the path (it must be a .wav, .mp3 or .flac file) or leave the box empty to use the built-in voice.', mbError, MB_OK);
      Result := False;
    end;
  if CurPageID = HuePage.ID then
    if HueCheck.Checked and (not ValidIp(Trim(HueIpEdit.Text))) then
    begin
      MsgBox('Please type the IP address of your Hue bridge, for example 192.168.1.20 (Hue app > Settings > Bridge), or untick Philips Hue.', mbError, MB_OK);
      Result := False;
    end;
  if CurPageID = SonosPage.ID then
    if SonosCheck.Checked and (not ValidIp(Trim(SonosIpEdit.Text))) then
    begin
      MsgBox('Please type the IP address of your Sonos speaker, for example 192.168.1.30 (Sonos app > Settings > System > About My System), or untick Sonos.', mbError, MB_OK);
      Result := False;
    end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var S, M: String;
begin
  S := MemoDirInfo + NewLine + NewLine + 'Your choices:' + NewLine;
  if HueCheck.Checked then S := S + Space + 'Philips Hue Smart Lights (bridge ' + Trim(HueIpEdit.Text) + ')' + NewLine;
  if TadoCheck.Checked then S := S + Space + 'Tado Smart Heating' + NewLine;
  if SonosCheck.Checked then S := S + Space + 'Sonos speaker (' + Trim(SonosIpEdit.Text) + ')' + NewLine;
  if WakeCheck.Checked then S := S + Space + 'Wake word "Hey Jarvis"' + NewLine;
  if RbOnYes.Checked and (OnlineRepo <> '') then M := 'newest found online' + NewLine + Space + Space + OnlineRepo + ' (about ' + OnlineGB + ' GB)' + NewLine + Space + Space + '(tested after the download)'
  else if RbExist.Checked and (ModelCombo.ItemIndex >= 0) then M := 'existing model ' + ModelKeys[ModelCombo.ItemIndex]
  else if RbT1.Checked then M := 'download about ' + TierGbs[1] + ' GB (' + TierIds[1] + ')'
  else if RbT2.Checked then M := 'download about ' + TierGbs[2] + ' GB (' + TierIds[2] + ')'
  else if RbT3.Checked then M := 'download about ' + TierGbs[3] + ' GB (' + TierIds[3] + ')'
  else M := 'none (later in LM Studio)';
  S := S + Space + 'Language model: ' + M + NewLine;
  S := S + Space + 'Speech recognition: Whisper ' + WhisperId(WhisperCombo.ItemIndex) + NewLine;
  if VoiceRbChatterbox.Checked then
  begin
    S := S + Space + 'Voice: Chatterbox' + NewLine + Space + Space + '(several GB of graphics card packages, can take long)';
    if Trim(ClipEdit.Text) <> '' then S := S + ', your own voice clip';
    S := S + NewLine;
  end
  else S := S + Space + 'Voice: Kokoro' + NewLine;
  if RagCheck.Checked then S := S + Space + 'Document search (Big RAG)' + NewLine;
  if Trim(KeyEdit.Text) <> '' then S := S + Space + 'Web search key (Firecrawl): entered' + NewLine;
  if Trim(CityEdit.Text) <> '' then S := S + Space + 'City (weather): ' + Trim(CityEdit.Text) + NewLine;
  if LmStudioInstalled then
    S := S + Space + 'LM Studio: already installed' + NewLine
  else
    S := S + Space + 'LM Studio: will be installed' + NewLine;
  S := S + Space + 'Fan monitor (LibreHardwareMonitor) for the HUD fan panel' + NewLine + Space + Space + '(Windows asks for administrator permission once)' + NewLine;
  if (not RbSkip.Checked) and (not RbExist.Checked) then S := S + Space + '(a model download of several GB can take a very long' + NewLine + Space + 'time; the setup waits for it)' + NewLine;
  S := S + NewLine + 'Other missing programs (Git, uv, Node.js, Rust,' + NewLine + 'Windows Terminal) are installed with winget;' + NewLine + 'Windows may ask for permission.';
  Result := S;
end;

{ ---------- running the setup script with live progress ---------- }

{ reads the status file, updates the bar and text, returns the script's exit code once an EXIT line exists, else -999 }
function ReadStatus: Integer;
var Lines: TArrayOfString; I, P, N: Integer; L: String; Shown: Boolean;
begin
  Result := -999;
  Shown := False;
  if LoadStringsFromFile(StatusPath, Lines) then
    for I := GetArrayLength(Lines) - 1 downto 0 do
    begin
      L := Lines[I];
      if (Result = -999) and (Pos('EXIT|', L) = 1) then Result := StrToIntDef(Copy(L, 6, 20), -1);
      if Shown then Continue;
      if Pos('STEP ', L) = 1 then
      begin
        P := Pos('|', L);
        if P > 6 then
        begin
          N := StrToIntDef(Copy(L, 6, P - 6), 0);
          WizardForm.ProgressGauge.Position := N;
          WizardForm.StatusLabel.Caption := 'Step ' + IntToStr(N) + ' of 10: ' + Copy(L, P + 1, 200);
        end;
        Shown := True;
      end;
    end;
end;

procedure RunSetup;
var Opts, Params, Clip, CityArg: String; Run, Code, Rc, Ticks: Integer; Lines: TArrayOfString;
begin
  Opts := '';
  if HueCheck.Checked then Opts := Opts + ' -WantHue -HueIp ''' + Trim(HueIpEdit.Text) + '''';
  if TadoCheck.Checked then Opts := Opts + ' -WantTado';
  if SonosCheck.Checked then Opts := Opts + ' -WantSonos -SonosIp ''' + Trim(SonosIpEdit.Text) + '''';
  if WakeCheck.Checked then Opts := Opts + ' -WantWake';
  if RagCheck.Checked then Opts := Opts + ' -WantRag';
  if RbOnYes.Checked and (OnlineRepo <> '') then Opts := Opts + ' -OnlineModel ''' + OnlineRepo + '''';
  if RbExist.Checked and (ModelCombo.ItemIndex >= 0) then Opts := Opts + ' -ModelId ''' + ModelKeys[ModelCombo.ItemIndex] + ''''
  else if RbT1.Checked then Opts := Opts + ' -ModelTier 1'
  else if RbT2.Checked then Opts := Opts + ' -ModelTier 2'
  else if RbT3.Checked then Opts := Opts + ' -ModelTier 3';
  Opts := Opts + ' -WhisperModel ''' + WhisperId(WhisperCombo.ItemIndex) + '''';
  if VoiceRbChatterbox.Checked then
  begin
    Opts := Opts + ' -TtsChoice ''chatterbox''';
    Clip := Trim(ClipEdit.Text);
    if Clip <> '' then
    begin
      StringChangeEx(Clip, '''', '''''', True);
      Opts := Opts + ' -VoiceClip ''' + Clip + '''';
    end;
  end
  else Opts := Opts + ' -TtsChoice ''kokoro''';
  CityArg := Trim(CityEdit.Text);
  if CityArg <> '' then
  begin
    StringChangeEx(CityArg, '"', '', True);
    StringChangeEx(CityArg, '''', '''''', True);
    Opts := Opts + ' -City ''' + CityArg + '''';
  end;
  { the key goes through this process's environment, never through a command line }
  if Trim(KeyEdit.Text) <> '' then SetEnvironmentVariableW('JARVIS_FIRECRAWL_KEY', Trim(KeyEdit.Text));
  if HueCheck.Checked then
    MsgBox('Press the round button on top of your Hue bridge, then click OK. The setup pairs with the bridge right away (the button is only valid for about 30 seconds).', mbInformation, MB_OK);

  WizardForm.FilenameLabel.Caption := '';
  WizardForm.ProgressGauge.Min := 0;
  WizardForm.ProgressGauge.Max := 10;
  WizardForm.ProgressGauge.Position := 0;
  WizardForm.StatusLabel.Caption := 'Starting the setup script...';
  Code := 0;
  for Run := 1 to 3 do
  begin
    DeleteFile(StatusPath);
    { the command runs the script, then writes its exit code as an EXIT line (single quotes inside, no $ expansion by Inno) }
    Params := '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$PID | Set-Content -LiteralPath ''' + StatusPath + '.pid''; & ''' + ExpandConstant('{app}\install-jarvis.ps1') + ''' -FromWizard -StatusFile ''' + StatusPath + '''' + Opts + '; Add-Content -LiteralPath ''' + StatusPath + ''' (''EXIT|'' + $LASTEXITCODE)"';
    if not Exec(PsExe, Params, ExpandConstant('{app}'), SW_HIDE, ewNoWait, Rc) then
    begin
      Code := -1;
      Break;
    end;
    { poll the status file until the EXIT line appears (at most 3 hours) }
    Ticks := 0;
    Code := ReadStatus;
    while Code = -999 do
    begin
      Sleep(400);
      PumpMessages;
      Code := ReadStatus;
      Ticks := Ticks + 1;
      if Ticks > 27000 then Code := -2;
    end;
    { make sure no setup process lingers (a window left open at the end): end the script's process tree }
    if LoadStringsFromFile(StatusPath + '.pid', Lines) and (GetArrayLength(Lines) > 0) then
      Exec('taskkill.exe', '/PID ' + Trim(Lines[0]) + ' /T /F', '', SW_HIDE, ewWaitUntilTerminated, Rc);
    { exit code 10 = programs were just installed; start the script again in a fresh process so it finds them }
    if Code <> 10 then Break;
    WizardForm.StatusLabel.Caption := 'Programs installed. Continuing in a fresh process...';
  end;
  SetupCode := Code;
  WizardForm.ProgressGauge.Position := 10;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then RunSetup;
end;

{ puts the block of controls of a custom page in the middle of the page (equal space left/right and top/bottom) }
procedure CenterPage(Page: TWizardPage);
var I: Integer; C: TControl; MinL, MinT, MaxR, MaxB, DX, DY: Integer;
begin
  if Page.Surface.ControlCount = 0 then Exit;
  MinL := 100000; MinT := 100000; MaxR := 0; MaxB := 0;
  for I := 0 to Page.Surface.ControlCount - 1 do
  begin
    C := Page.Surface.Controls[I];
    if C.Visible then
    begin
      if C.Left < MinL then MinL := C.Left;
      if C.Top < MinT then MinT := C.Top;
      if C.Left + C.Width > MaxR then MaxR := C.Left + C.Width;
      if C.Top + C.Height > MaxB then MaxB := C.Top + C.Height;
    end;
  end;
  if MaxR <= MinL then Exit;
  DX := ((Page.SurfaceWidth - (MaxR - MinL)) div 2) - MinL;
  DY := ((Page.SurfaceHeight - (MaxB - MinT)) div 2) - MinT;
  if DX < 0 then DX := 0;
  if DY < 0 then DY := -MinT;   { too tall: start at the top }
  for I := 0 to Page.Surface.ControlCount - 1 do
  begin
    C := Page.Surface.Controls[I];
    C.Left := C.Left + DX;
    C.Top := C.Top + DY;
  end;
end;

procedure WizardResize(Sender: TObject);
begin
  if (WizardForm.CurPageID >= 100) and (WizardForm.CurPageID <> wpFinished) then CenterPage(PageFromID(WizardForm.CurPageID));
end;

procedure CurPageChanged(CurPageID: Integer);
var S: String;
begin
  if (CurPageID = ModelPage.ID) and (not ModelsDetected) then DetectModels;
  if CurPageID = VoicePage.ID then DetectVoice;
  if (CurPageID >= 100) and (CurPageID <> wpFinished) then CenterPage(PageFromID(CurPageID));
  if CurPageID = wpFinished then
  begin
    S := '';
    if SetupCode <> 0 then
      S := 'The setup script ended with code ' + IntToStr(SetupCode) + '. Details: ' + ExpandConstant('{%USERPROFILE}\.openjarvis\install-log.txt') + #13#10#13#10;
    S := S + 'Still to do:' + #13#10 +
      '1. Double-click the Jarvis icon on your desktop. Allow the microphone in your browser and remember the decision.' + #13#10 +
      '2. No language model chosen or the download failed? Open LM Studio, download one, then run this installer again.' + #13#10;
    if RagCheck.Checked then
      S := S + '3. Document search: in LM Studio open a chat, enable the Big RAG plugin and set the documents folder, an index folder and the embedding model (README, Document search).' + #13#10;
    if TadoCheck.Checked then
      S := S + '4. Tado login did not finish? Run tools\tado_login.py in the Jarvis folder.' + #13#10;
    S := S + 'Optional: to use the HUD from your phone or another PC in your home network, run tools\setup-remote-access.ps1 in the Jarvis folder (README).' + #13#10;
    WizardForm.FinishedLabel.Caption := S;
  end;
end;

{ ---------- uninstaller in HUD colors (the confirmation boxes stay Windows style) ---------- }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Rc: Integer; Names: TArrayOfString; I: Integer; Desk: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    { 1. stop everything that runs from the folder (otherwise Windows keeps its files locked); LM Studio is left running }
    if FileExists(ExpandConstant('{app}\tools\stop-jarvis.ps1')) then
      Exec(PsExe, '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{app}\tools\stop-jarvis.ps1') + '" -KeepLmStudio', '', SW_HIDE, ewWaitUntilTerminated, Rc);
    { 2. the two desktop icons made by the setup script }
    Desk := ExpandConstant('{userdesktop}');
    DeleteFile(Desk + '\Jarvis.lnk');
    DeleteFile(Desk + '\Stop Jarvis.lnk');
    { 3b. what the optional parts added to Windows: the fan monitor (its folder only if our setup put it there, marker file)
          and the firewall rule of the LAN gateway; Windows asks for administrator permission }
    if (FileExists(ExpandConstant('{pf}\LibreHardwareMonitor\installed-by-ironman-jarvis.txt')) or DirExists(ExpandConstant('{%USERPROFILE}\.openjarvis\gateway')))
       and FileExists(ExpandConstant('{app}\tools\remove-windows-parts.ps1')) then
      if SuppressibleMsgBox('Also remove the fan monitor (LibreHardwareMonitor, if this setup installed it) and the firewall rules for the HUD (ports 8085 and 8443)?' + #13#10 + 'Windows will ask for administrator permission.', mbConfirmation, MB_YESNO, IDYES) = IDYES then
        ShellExec('runas', 'powershell.exe', '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{app}\tools\remove-windows-parts.ps1') + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc);
    { 4. settings, keys and logs: ask (they hold the Hue key, the Tado login and your saved chat/memory data) }
    if DirExists(ExpandConstant('{%USERPROFILE}\.openjarvis')) then
      if SuppressibleMsgBox('Also delete your Jarvis settings, keys and logs?' + #13#10 + ExpandConstant('{%USERPROFILE}\.openjarvis') + #13#10#13#10 + 'Choose No to keep them for a later reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      begin
        DelTree(ExpandConstant('{%USERPROFILE}\.openjarvis'), True, True, True);
        { the user settings made by the setup script (Hue address, web search key) go together with the settings folder; kept otherwise, so a reinstall finds them.
          Same names as $JarvisUserEnvVars in tools\jarvis-common.ps1 (tests\powershell\wizard-contract.Tests.ps1 checks that they match) }
        SetArrayLength(Names, 6);
        Names[0] := 'HUE_BRIDGE_IP'; Names[1] := 'FIRECRAWL_API_KEY'; Names[2] := 'OPENJARVIS_WEB_SEARCH_ENGINE';
        Names[3] := 'JARVIS_DOC_ROOT'; Names[4] := 'SERPLY_API_KEY'; Names[5] := 'SONOS_IP';
        for I := 0 to 5 do RegDeleteValue(HKEY_CURRENT_USER, 'Environment', Names[I]);
      end;
  end;
end;

procedure InitializeUninstallProgressForm;
begin
  ThemeFrame(UninstallProgressForm.Handle);
  UninstallProgressForm.Color := CBg;
  UninstallProgressForm.MainPanel.Color := CBg;
  UninstallProgressForm.InnerPage.Color := CBg;
  UninstallProgressForm.PageNameLabel.Font.Color := CCyan;
  UninstallProgressForm.PageDescriptionLabel.Font.Color := CText;
  UninstallProgressForm.StatusLabel.Font.Color := COrange;
end;
