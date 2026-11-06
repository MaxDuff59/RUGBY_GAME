import { useScenePrefs } from "../scene/prefs.js";

// Les réglages des scènes 3D en match (src/scene/prefs.js) : les montrer ou non, et
// leur son ; le terrain 2D du match en direct. Dans le pied du menu, et dans le volet
// « Plus » sur téléphone.
export default function ScenePrefs({ className = "" }) {
  const [prefs, setPrefs] = useScenePrefs();
  return (
    <div className={`scene-prefs${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className="link-button"
        aria-pressed={prefs.scenes}
        title="Certaines décisions en match se jouent en 3D plutôt que dans une fenêtre de texte"
        onClick={() => setPrefs({ scenes: !prefs.scenes })}
      >
        Scènes 3D : {prefs.scenes ? "oui" : "non"}
      </button>
      <button type="button" className="link-button" aria-pressed={prefs.sound} onClick={() => setPrefs({ sound: !prefs.sound })}>
        Son : {prefs.sound ? "oui" : "non"}
      </button>
      <button
        type="button"
        className="link-button"
        aria-pressed={prefs.pitch}
        title="Le match en direct montre les joueurs sur un terrain vu de dessus"
        onClick={() => setPrefs({ pitch: !prefs.pitch })}
      >
        Terrain 2D : {prefs.pitch ? "oui" : "non"}
      </button>
    </div>
  );
}
