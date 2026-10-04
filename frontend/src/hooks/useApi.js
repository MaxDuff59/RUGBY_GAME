import { useCallback, useEffect, useState } from "react";

// Charge une ressource de l'API et expose son état : { data, error, loading, reload }.
// `load` doit être stable (useCallback) ou définie hors composant, sinon elle
// relancerait l'appel à chaque rendu.
export function useApi(load) {
  const [state, setState] = useState({ data: null, error: null, loading: true });

  const run = useCallback(() => {
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true }));
    load()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setState({ data: null, error, loading: false }));
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(run, [run]);

  return { ...state, reload: run };
}
