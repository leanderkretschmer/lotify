//
//  ContentView.swift
//  lotify
//
//  Created by Leander Kretschmer on 28.07.25.
//

import SwiftUI
import CryptoKit
import Security

struct ContentView: View {
    @State private var cdnServer: String = ""
    @State private var messagingServer: String = "lotify.kretschmer-leander.de"
    @State private var showMainView = false
    @State private var publicKey: String = "(wird generiert...)"
    @State private var showSettings = false
    @State private var showResetAlert = false
    @State private var showResetConfirm = false
    
    private let privateKeyTag = "de.kretschmer.lotify.privatekey"
    
    init() {
        if let pubKey = Self.loadOrCreateKeyPair(tag: privateKeyTag) {
            _publicKey = State(initialValue: pubKey)
        }
    }
    
    var body: some View {
        if showMainView {
            MainMessageView(
                cdnServer: cdnServer,
                messagingServer: messagingServer,
                publicKey: publicKey,
                onShowSettings: { showSettings = true }
            )
            .sheet(isPresented: $showSettings) {
                SettingsView(
                    cdnServer: $cdnServer,
                    messagingServer: $messagingServer,
                    publicKey: publicKey,
                    onResetKeys: { showResetAlert = true }
                )
            }
            .alert(isPresented: $showResetAlert) {
                Alert(
                    title: Text("Schlüssel wirklich zurücksetzen?"),
                    message: Text("Der private und öffentliche Schlüssel werden unwiderruflich gelöscht und neu generiert. Fortfahren?"),
                    primaryButton: .destructive(Text("Zurücksetzen")) {
                        showResetConfirm = true
                    },
                    secondaryButton: .cancel()
                )
            }
            .alert(isPresented: $showResetConfirm) {
                Alert(
                    title: Text("Wirklich sicher?"),
                    message: Text("Das Zurücksetzen kann nicht rückgängig gemacht werden!"),
                    primaryButton: .destructive(Text("Ja, endgültig zurücksetzen")) {
                        Self.deleteKeyFromKeychain(tag: privateKeyTag)
                        if let pubKey = Self.loadOrCreateKeyPair(tag: privateKeyTag) {
                            publicKey = pubKey
                        }
                        showResetConfirm = false
                        showResetAlert = false
                    },
                    secondaryButton: .cancel {
                        showResetConfirm = false
                        showResetAlert = false
                    }
                )
            }
        } else {
            StartScreen(
                cdnServer: $cdnServer,
                messagingServer: $messagingServer,
                onContinue: { showMainView = true }
            )
        }
    }
    
    static func loadOrCreateKeyPair(tag: String) -> String? {
        // Versuche, privaten Schlüssel aus Schlüsselbund zu laden
        if let privateKeyData = loadKeyFromKeychain(tag: tag) {
            if let privateKey = try? Curve25519.KeyAgreement.PrivateKey(rawRepresentation: privateKeyData) {
                let pubKey = privateKey.publicKey.rawRepresentation.base64EncodedString()
                return pubKey
            }
        }
        // Erzeuge neues Schlüsselpaar
        let privateKey = Curve25519.KeyAgreement.PrivateKey()
        let privateKeyData = privateKey.rawRepresentation
        saveKeyToKeychain(tag: tag, keyData: privateKeyData)
        let pubKey = privateKey.publicKey.rawRepresentation.base64EncodedString()
        return pubKey
    }
    
    static func loadKeyFromKeychain(tag: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassKey,
            kSecAttrApplicationTag as String: tag,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecSuccess {
            return item as? Data
        }
        return nil
    }
    
    static func saveKeyToKeychain(tag: String, keyData: Data) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassKey,
            kSecAttrApplicationTag as String: tag,
            kSecValueData as String: keyData,
            kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom
        ]
        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }
    
    static func deleteKeyFromKeychain(tag: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassKey,
            kSecAttrApplicationTag as String: tag
        ]
        SecItemDelete(query as CFDictionary)
    }
}

struct StartScreen: View {
    @Binding var cdnServer: String
    @Binding var messagingServer: String
    let onContinue: () -> Void
    var body: some View {
        VStack(spacing: 32) {
            Image(systemName: "bolt.horizontal.circle.fill")
                .resizable()
                .frame(width: 64, height: 64)
                .foregroundColor(Color("LotifyPrimary"))
                .padding(.top, 40)
            Text("Willkommen bei Lotify")
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(Color("LotifyPrimary"))
            VStack(alignment: .leading, spacing: 16) {
                TextField("CDN-Server (optional)", text: $cdnServer)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                TextField("Messaging-Server (optional)", text: $messagingServer)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .foregroundColor(.secondary)
                    .font(.footnote)
            }
            Button(action: onContinue) {
                Text("Weiter")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color("LotifyPrimary"))
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
            Spacer()
        }
        .padding(.horizontal, 32)
        .frame(maxWidth: 400)
    }
}

struct SettingsView: View {
    @Binding var cdnServer: String
    @Binding var messagingServer: String
    let publicKey: String
    let onResetKeys: () -> Void
    var body: some View {
        VStack(spacing: 24) {
            Text("Zugangsdaten ändern")
                .font(.headline)
            TextField("CDN-Server (optional)", text: $cdnServer)
                .textFieldStyle(RoundedBorderTextFieldStyle())
            TextField("Messaging-Server (optional)", text: $messagingServer)
                .textFieldStyle(RoundedBorderTextFieldStyle())
            VStack(alignment: .leading, spacing: 8) {
                Text("Öffentlicher Schlüssel:")
                    .font(.caption)
                    .foregroundColor(.secondary)
                HStack {
                    Text(publicKey)
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Button(action: {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(publicKey, forType: .string)
                    }) {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(BorderlessButtonStyle())
                    .help("Kopieren")
                }
            }
            Button(action: onResetKeys) {
                Text("Schlüssel zurücksetzen…")
                    .foregroundColor(.red)
            }
            Spacer()
        }
        .padding(32)
        .frame(maxWidth: 400)
    }
}

struct MainMessageView: View {
    let cdnServer: String
    let messagingServer: String
    let publicKey: String
    let onShowSettings: () -> Void
    
    var body: some View {
        VStack {
            HStack {
                Button(action: onShowSettings) {
                    Image(systemName: "gearshape")
                        .imageScale(.large)
                        .foregroundColor(Color("LotifyPrimary"))
                }
                .buttonStyle(BorderlessButtonStyle())
                .help("Zugangsdaten & Schlüssel verwalten")
                Spacer()
            }
            .padding([.top, .leading], 16)
            Text("Nachrichtenliste kommt hier hin…")
                .foregroundColor(Color("LotifyPrimary"))
            // Hier folgt später die Nachrichtenliste
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.windowBackgroundColor))
    }
}

#Preview {
    ContentView()
}
