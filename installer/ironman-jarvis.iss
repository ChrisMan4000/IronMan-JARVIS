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
OutputDir=.
OutputBaseFilename=IronMan-JARVIS-Installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=wizard-side.bmp,wizard-side-150.bmp,wizard-side-200.bmp
WizardSmallImageFile=wizard-small.bmp,wizard-small-200.bmp
SetupIconFile=..\assets\jarvis.ico

[Messages]
WelcomeLabel1=IronMan J.A.R.V.I.S.
WelcomeLabel2=A private AI assistant with a full-screen HUD. The AI runs on your own PC (LM Studio), nothing is sent to a cloud AI.%n%nOn the next pages you choose the optional parts. Each one has a link where you can read more first.%n%nBased on OpenJarvis (https://github.com/open-jarvis/OpenJarvis, Apache-2.0). Vibecoded with the free version of Claude. Not yet tested on a freshly wiped PC.
FinishedHeadingLabel=Setup finished

[Files]
Source: "..\*"; DestDir: "{app}"; Excludes: "installer\*,.git\*"; Flags: recursesubdirs createallsubdirs
Source: "list-llms.ps1"; Flags: dontcopy

[UninstallDelete]
; the setup script creates the Python environment, node_modules, caches and logs inside the folder: remove all of it
Type: filesandordirs; Name: "{app}"

[Code]
const
  CBg     = $18120B;   { #0b1218 }
  CCyan   = $FFD319;   { #19d3ff }
  COrange = $3D9AFF;   { #ff9a3d }
  CText   = $F5E9BF;   { #bfe9f5 }
  T1Text  = 'About 2.5 GB   qwen/qwen3-4b-2507   (small and fast, simpler answers)';
  T2Text  = 'About 6.7 GB   google/gemma-4-12b-qat   (good balance for 12-16 GB graphics cards)';
  T3Text  = 'About 14.6 GB   google/gemma-4-26b-a4b-qat   (best quality, needs about 24 GB GPU memory)';

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
  HuePage, TadoPage, WakePage, ModelPage, RagPage, KeyPage: TWizardPage;
  HueCheck, TadoCheck, WakeCheck, RagCheck: TNewCheckBox;
  HueIpEdit, KeyEdit: TNewEdit;
  RbExist, RbT1, RbT2, RbT3, RbSkip: TNewRadioButton;
  ModelCombo: TNewComboBox;
  ModelInfo: TNewStaticText;
  ModelKeys: TArrayOfString;
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
end;

procedure SetRadioText(R: TNewRadioButton; const Txt: String);
begin
  Lbls[R.Tag].Caption := Txt;
end;

procedure SetRadioLook(R: TNewRadioButton);
begin
  if R.Enabled then Lbls[R.Tag].Font.Color := CText else Lbls[R.Tag].Font.Color := $707070;
end;

procedure ThemeWizard;
begin
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

procedure ModelRadioClick(Sender: TObject);
begin
  ModelCombo.Enabled := RbExist.Checked and RbExist.Enabled;
end;

procedure CheckLabelClick(Sender: TObject);
var C: TNewCheckBox;
begin
  C := CheckList[TNewStaticText(Sender).Tag];
  C.Checked := not C.Checked;
  HueClick(nil);
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

{ ---------- pages ---------- }

procedure InitializeWizard;
var Y: Integer; T: TNewStaticText;
begin
  ThemeWizard;
  StatusPath := ExpandConstant('{tmp}\jarvis-status.txt');
  ModelsDetected := False;
  SetupCode := 0;

  { Philips Hue }
  HuePage := NewPage(wpSelectDir, 'Philips Hue lights (optional)', 'Switch your lights on and off by voice or text.');
  Y := 0;
  AddText(HuePage, Y, 'Lets Jarvis switch your Philips Hue lights on and off ("turn off the kitchen lights"). Every change is read back from the bridge. Needs a Hue bridge in your home network.', CText, False);
  AddLink(HuePage, Y, 'Philips Hue', 'https://www.philips-hue.com/en-us/explore-hue');
  HueCheck := AddCheck(HuePage, Y, 'Use Philips Hue lights');
  HueCheck.OnClick := @HueClick;
  AddText(HuePage, Y, 'IP address of your Hue bridge (Hue app > Settings > Bridge):', CText, False);
  HueIpEdit := TNewEdit.Create(HuePage);
  HueIpEdit.Parent := HuePage.Surface;
  HueIpEdit.Left := 0; HueIpEdit.Top := Y; HueIpEdit.Width := ScaleX(160);
  HueIpEdit.Enabled := False;
  Y := Y + ScaleY(30);
  AddText(HuePage, Y, 'When the installation starts, a message asks you to press the round button on top of the bridge.', COrange, False);

  { Tado }
  TadoPage := NewPage(HuePage.ID, 'Tado heating (optional)', 'Control your Tado radiator valves.');
  Y := 0;
  AddText(TadoPage, Y, 'Lets Jarvis set or switch off your Tado heating ("heating off in the living room"). Needs a Tado account. Your browser opens once so you can approve the login.', CText, False);
  AddLink(TadoPage, Y, 'Tado', 'https://www.tado.com/en');
  TadoCheck := AddCheck(TadoPage, Y, 'Use Tado heating');

  { wake word }
  WakePage := NewPage(TadoPage.ID, 'Wake word (optional)', 'Say "Hey Jarvis" to start talking.');
  Y := 0;
  AddText(WakePage, Y, 'Listens for "Hey Jarvis" with the open-source openWakeWord. It needs its own Python environment and a few hundred MB, a few minutes of setup. Without it you click the ring or press F6.', CText, False);
  AddLink(WakePage, Y, 'openWakeWord', 'https://github.com/dscripka/openWakeWord');
  WakeCheck := AddCheck(WakePage, Y, 'Set up the wake word "Hey Jarvis"');

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
  RbT1 := AddRadio(ModelPage, Y, T1Text);
  RbT2 := AddRadio(ModelPage, Y, T2Text);
  RbT3 := AddRadio(ModelPage, Y, T3Text);
  RbSkip := AddRadio(ModelPage, Y, 'Skip (I will download a model in LM Studio myself)');
  RbExist.Enabled := False;
  SetRadioLook(RbExist);
  RbT1.Checked := True;
  RbExist.OnClick := @ModelRadioClick; RbT1.OnClick := @ModelRadioClick; RbT2.OnClick := @ModelRadioClick;
  RbT3.OnClick := @ModelRadioClick; RbSkip.OnClick := @ModelRadioClick;

  { document search }
  RagPage := NewPage(ModelPage.ID, 'Document search (optional, experimental)', 'Ask questions about your own PDF, Word and text files.');
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
end;

procedure DetectModels;
var Lines: TArrayOfString; I, N, Rc, Tier: Integer; L, F, Gpu, Ram, Tmp, Mark, M: String;
begin
  ModelsDetected := True;
  Tier := 1; Gpu := '0'; Ram := '?';
  Tmp := ExpandConstant('{tmp}\llms.txt');
  ExtractTemporaryFile('list-llms.ps1');
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{tmp}\list-llms.ps1') + '" -Out "' + Tmp + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc);
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
      else if L <> '' then
      begin
        F := NextField(L);
        if ValidModelId(F) then
        begin
          N := GetArrayLength(ModelKeys);
          SetArrayLength(ModelKeys, N + 1);
          ModelKeys[N] := F;
          ModelCombo.Items.Add(F + '  (' + L + ' GB)');
        end;
      end;
    end;
  LmFound := FileExists(ExpandConstant('{localappdata}\Programs\LM Studio\LM Studio.exe')) or FileExists(ExpandConstant('{pf}\LM Studio\LM Studio.exe')) or FileExists(ExpandConstant('{%USERPROFILE}\.lmstudio\bin\lms.exe'));
  if LmFound then M := 'LM Studio: found on this PC.' else M := 'LM Studio: not found. The setup installs it for you (winget).';
  ModelInfo.Caption := M + #13#10 + 'Your PC: GPU memory ' + Gpu + ' GB, RAM ' + Ram + ' GB. The recommended size is marked.';
  Mark := '   <-- recommended';
  if Tier = 1 then SetRadioText(RbT1, T1Text + Mark);
  if Tier = 2 then SetRadioText(RbT2, T2Text + Mark);
  if Tier = 3 then SetRadioText(RbT3, T3Text + Mark);
  RbT1.Checked := Tier = 1; RbT2.Checked := Tier = 2; RbT3.Checked := Tier = 3;
  if ModelCombo.Items.Count > 0 then
  begin
    RbExist.Enabled := True;
    SetRadioLook(RbExist);
    ModelCombo.ItemIndex := 0;
    RbExist.Checked := True;
  end;
  ModelRadioClick(nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = HuePage.ID then
    if HueCheck.Checked and (not ValidIp(Trim(HueIpEdit.Text))) then
    begin
      MsgBox('Please type the IP address of your Hue bridge, for example 192.168.1.20 (Hue app > Settings > Bridge), or untick Philips Hue.', mbError, MB_OK);
      Result := False;
    end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var S, M: String;
begin
  S := MemoDirInfo + NewLine + NewLine + 'Your choices:' + NewLine;
  if HueCheck.Checked then S := S + Space + 'Philips Hue (bridge ' + Trim(HueIpEdit.Text) + ')' + NewLine;
  if TadoCheck.Checked then S := S + Space + 'Tado heating' + NewLine;
  if WakeCheck.Checked then S := S + Space + 'Wake word "Hey Jarvis"' + NewLine;
  if RbExist.Checked and (ModelCombo.ItemIndex >= 0) then M := 'existing model ' + ModelKeys[ModelCombo.ItemIndex]
  else if RbT1.Checked then M := 'download about 2.5 GB'
  else if RbT2.Checked then M := 'download about 6.7 GB'
  else if RbT3.Checked then M := 'download about 14.6 GB'
  else M := 'none (later in LM Studio)';
  S := S + Space + 'Language model: ' + M + NewLine;
  if RagCheck.Checked then S := S + Space + 'Document search (Big RAG)' + NewLine;
  if Trim(KeyEdit.Text) <> '' then S := S + Space + 'Web search key (Firecrawl): entered' + NewLine;
  if FileExists(ExpandConstant('{localappdata}\Programs\LM Studio\LM Studio.exe')) or FileExists(ExpandConstant('{pf}\LM Studio\LM Studio.exe')) or FileExists(ExpandConstant('{%USERPROFILE}\.lmstudio\bin\lms.exe')) then
    S := S + Space + 'LM Studio: already installed' + NewLine
  else
    S := S + Space + 'LM Studio: will be installed' + NewLine;
  S := S + Space + 'Fan monitor (LibreHardwareMonitor): installed for the HUD fan panel, Windows asks for administrator permission once' + NewLine;
  S := S + NewLine + 'Other missing programs (Git, uv, Node.js, Rust, Windows Terminal) are installed with winget; Windows may ask for permission.';
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
var Opts, Params: String; Run, Code, Rc, Ticks: Integer;
begin
  Opts := '';
  if HueCheck.Checked then Opts := Opts + ' -WantHue -HueIp ''' + Trim(HueIpEdit.Text) + '''';
  if TadoCheck.Checked then Opts := Opts + ' -WantTado';
  if WakeCheck.Checked then Opts := Opts + ' -WantWake';
  if RagCheck.Checked then Opts := Opts + ' -WantRag';
  if RbExist.Checked and (ModelCombo.ItemIndex >= 0) then Opts := Opts + ' -ModelId ''' + ModelKeys[ModelCombo.ItemIndex] + ''''
  else if RbT1.Checked then Opts := Opts + ' -ModelTier 1'
  else if RbT2.Checked then Opts := Opts + ' -ModelTier 2'
  else if RbT3.Checked then Opts := Opts + ' -ModelTier 3';
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
    Params := '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "& ''' + ExpandConstant('{app}\install-jarvis.ps1') + ''' -FromWizard -StatusFile ''' + StatusPath + '''' + Opts + '; Add-Content -LiteralPath ''' + StatusPath + ''' (''EXIT|'' + $LASTEXITCODE)"';
    if not Exec('powershell.exe', Params, ExpandConstant('{app}'), SW_HIDE, ewNoWait, Rc) then
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

procedure CurPageChanged(CurPageID: Integer);
var S: String;
begin
  if (CurPageID = ModelPage.ID) and (not ModelsDetected) then DetectModels;
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
      Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{app}\tools\stop-jarvis.ps1') + '" -KeepLmStudio', '', SW_HIDE, ewWaitUntilTerminated, Rc);
    { 2. the two desktop icons made by the setup script }
    Desk := ExpandConstant('{userdesktop}');
    DeleteFile(Desk + '\Jarvis.lnk');
    DeleteFile(Desk + '\Stop Jarvis.lnk');
    { 3. the user settings made by the setup script }
    SetArrayLength(Names, 5);
    Names[0] := 'HUE_BRIDGE_IP'; Names[1] := 'FIRECRAWL_API_KEY'; Names[2] := 'OPENJARVIS_WEB_SEARCH_ENGINE';
    Names[3] := 'JARVIS_DOC_ROOT'; Names[4] := 'SERPLY_API_KEY';
    for I := 0 to 4 do RegDeleteValue(HKEY_CURRENT_USER, 'Environment', Names[I]);
    { 3b. the fan monitor, only if our installer put it there (marker file); Windows asks for administrator permission }
    if FileExists(ExpandConstant('{pf}\LibreHardwareMonitor\installed-by-ironman-jarvis.txt')) and FileExists(ExpandConstant('{app}\tools\remove-fan-monitor.ps1')) then
      if SuppressibleMsgBox('Also remove the fan monitor (LibreHardwareMonitor) that this setup installed?' + #13#10 + 'Windows will ask for administrator permission.', mbConfirmation, MB_YESNO, IDYES) = IDYES then
        ShellExec('runas', 'powershell.exe', '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{app}\tools\remove-fan-monitor.ps1') + '"', '', SW_HIDE, ewWaitUntilTerminated, Rc);
    { 4. settings, keys and logs: ask (they hold the Hue key, the Tado login and your saved chat/memory data) }
    if DirExists(ExpandConstant('{%USERPROFILE}\.openjarvis')) then
      if SuppressibleMsgBox('Also delete your Jarvis settings, keys and logs?' + #13#10 + ExpandConstant('{%USERPROFILE}\.openjarvis') + #13#10#13#10 + 'Choose No to keep them for a later reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(ExpandConstant('{%USERPROFILE}\.openjarvis'), True, True, True);
  end;
end;

procedure InitializeUninstallProgressForm;
begin
  UninstallProgressForm.Color := CBg;
  UninstallProgressForm.MainPanel.Color := CBg;
  UninstallProgressForm.InnerPage.Color := CBg;
  UninstallProgressForm.PageNameLabel.Font.Color := CCyan;
  UninstallProgressForm.PageDescriptionLabel.Font.Color := CText;
  UninstallProgressForm.StatusLabel.Font.Color := COrange;
end;
