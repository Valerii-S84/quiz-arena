import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  fetchAdminSession,
  fetchPromo,
  fetchPromoAudit,
  fetchPromoDetail,
  fetchPromoProducts,
  fetchPromoStats,
} from "@/lib/api";

import {
  copyPromoCodes,
  createBulkCodeModalState,
  createSingleCodeModalState,
} from "./promo-code-export";
import {
  buildBulkPromoPayload,
  buildCreatePromoPayload,
  buildPatchPromoPayload,
  createBulkPromoForm,
  createEmptyPromoForm,
  SEARCH_DEBOUNCE_MS,
} from "./promo-form";
import { createEditPromoFormValues } from "./promo-view-model";
import type {
  AdminSession,
  BulkGenerateResponse,
  CodeModalState,
  FlashState,
  PromoAuditResponse,
  PromoDetailTab,
  PromoFormValues,
  PromoItem,
  PromoListResponse,
  PromoProductsResponse,
  PromoStatsResponse,
  PromoStatusFilter,
  RevokeResponse,
} from "./promo-types";

export function usePromoClientState() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<PromoStatusFilter>("all");
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [flash, setFlash] = useState<FlashState | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [editPromo, setEditPromo] = useState<PromoItem | null>(null);
  const [createForm, setCreateForm] = useState<PromoFormValues>(createEmptyPromoForm());
  const [bulkForm, setBulkForm] = useState<PromoFormValues>(createBulkPromoForm());
  const [editForm, setEditForm] = useState<PromoFormValues>(createEmptyPromoForm());
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailTab, setDetailTab] = useState<PromoDetailTab>("params");
  const [revealedCode, setRevealedCode] = useState<string | null>(null);
  const [codeModal, setCodeModal] = useState<CodeModalState | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedSearch(searchInput.trim()),
      SEARCH_DEBOUNCE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const sessionQuery = useQuery<AdminSession>({
    queryKey: ["admin-session"],
    queryFn: fetchAdminSession,
  });
  const productsQuery = useQuery<PromoProductsResponse>({
    queryKey: ["promo-products"],
    queryFn: fetchPromoProducts,
  });
  const promoQuery = useQuery<PromoListResponse>({
    queryKey: ["promo-list", statusFilter, debouncedSearch],
    queryFn: () =>
      fetchPromo(
        statusFilter === "all" ? undefined : statusFilter,
        debouncedSearch || undefined,
      ),
  });
  const detailQuery = useQuery<PromoItem>({
    queryKey: ["promo-detail", detailId],
    queryFn: () => fetchPromoDetail(detailId as number),
    enabled: detailId !== null,
  });
  const statsQuery = useQuery<PromoStatsResponse>({
    queryKey: ["promo-stats", detailId],
    queryFn: () => fetchPromoStats(detailId as number),
    enabled: detailId !== null,
  });
  const auditQuery = useQuery<PromoAuditResponse>({
    queryKey: ["promo-audit", detailId],
    queryFn: () => fetchPromoAudit(detailId as number),
    enabled: detailId !== null,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/admin/promo", buildCreatePromoPayload(createForm));
      return data as PromoItem;
    },
    onSuccess: async (data) => {
      setCreateOpen(false);
      setCreateForm(createEmptyPromoForm());
      setCodeModal(createSingleCodeModalState(data));
      setFlash({ kind: "success", text: "Der Promo-Code wurde gespeichert." });
      await queryClient.invalidateQueries({ queryKey: ["promo-list"] });
    },
    onError: () =>
      setFlash({ kind: "error", text: "Der Promo-Code konnte nicht gespeichert werden." }),
  });

  const bulkMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(
        "/admin/promo/bulk-generate",
        buildBulkPromoPayload(bulkForm),
      );
      return data as BulkGenerateResponse;
    },
    onSuccess: async (data) => {
      setBulkOpen(false);
      setCodeModal(createBulkCodeModalState(bulkForm.campaignName, data));
      setFlash({ kind: "success", text: "Die Batch-Generierung ist abgeschlossen." });
      await queryClient.invalidateQueries({ queryKey: ["promo-list"] });
    },
    onError: () =>
      setFlash({ kind: "error", text: "Die Batch-Generierung ist fehlgeschlagen." }),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch(
        `/admin/promo/${editPromo?.id}`,
        buildPatchPromoPayload(editForm),
      );
      return data as PromoItem;
    },
    onSuccess: async () => {
      setEditPromo(null);
      setFlash({ kind: "success", text: "Die Änderungen wurden gespeichert." });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-list"] }),
        queryClient.invalidateQueries({ queryKey: ["promo-detail", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-stats", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-audit", detailId] }),
      ]);
    },
    onError: () =>
      setFlash({ kind: "error", text: "Die Änderungen konnten nicht gespeichert werden." }),
  });

  const toggleMutation = useMutation({
    mutationFn: async (promoId: number) => {
      const { data } = await api.patch(`/admin/promo/${promoId}/toggle`);
      return data as PromoItem;
    },
    onSuccess: async () => {
      setFlash({ kind: "success", text: "Der Status wurde aktualisiert." });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-list"] }),
        queryClient.invalidateQueries({ queryKey: ["promo-detail", detailId] }),
      ]);
    },
    onError: () =>
      setFlash({ kind: "error", text: "Der Status konnte nicht geändert werden." }),
  });

  const revokeMutation = useMutation({
    mutationFn: async ({ promoId, reason }: { promoId: number; reason: string | null }) => {
      const { data } = await api.post(`/admin/promo/${promoId}/revoke`, { reason });
      return data as RevokeResponse;
    },
    onSuccess: async (data) => {
      setFlash({
        kind: "success",
        text:
          data.revoked_count > 0
            ? `${data.revoked_count} Reservierungen wurden widerrufen.`
            : "Es gab keine aktiven Reservierungen.",
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-list"] }),
        queryClient.invalidateQueries({ queryKey: ["promo-stats", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-audit", detailId] }),
      ]);
    },
    onError: () =>
      setFlash({ kind: "error", text: "Der Widerruf ist fehlgeschlagen." }),
  });

  const revealMutation = useMutation({
    mutationFn: async (promoId: number) => {
      const data = await fetchPromoDetail(promoId, true);
      return data as PromoItem;
    },
    onSuccess: async (data) => {
      setRevealedCode(data.raw_code);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["promo-detail", detailId] }),
        queryClient.invalidateQueries({ queryKey: ["promo-audit", detailId] }),
      ]);
    },
  });

  function openEditModal(item: PromoItem) {
    setEditPromo(item);
    setEditForm(createEditPromoFormValues(item));
  }

  async function handleCopyAll() {
    if (!codeModal || codeModal.codes.length === 0) {
      return;
    }
    await copyPromoCodes(codeModal.codes.join("\n"));
    setFlash({
      kind: "success",
      text: "Die Codes wurden in die Zwischenablage kopiert.",
    });
  }

  async function handleRevoke(promoId: number) {
    const input = window.prompt("Optionaler Grund für den Widerruf", "");
    const reason = input === null ? null : input.trim() || null;
    await revokeMutation.mutateAsync({ promoId, reason });
  }

  function openDetailWithParams(promoId: number) {
    setDetailId(promoId);
    setDetailTab("params");
    setRevealedCode(null);
  }

  function openDetailWithStats(promoId: number) {
    setDetailId(promoId);
    setDetailTab("stats");
  }

  function closeCodeModal() {
    setCodeModal(null);
    void queryClient.invalidateQueries({ queryKey: ["promo-list"] });
  }

  return {
    statusFilter,
    setStatusFilter,
    searchInput,
    setSearchInput,
    flash,
    createOpen,
    setCreateOpen,
    bulkOpen,
    setBulkOpen,
    editPromo,
    setEditPromo,
    createForm,
    setCreateForm,
    bulkForm,
    setBulkForm,
    editForm,
    setEditForm,
    detailId,
    setDetailId,
    detailTab,
    setDetailTab,
    revealedCode,
    codeModal,
    sessionQuery,
    productsQuery,
    promoQuery,
    detailQuery,
    statsQuery,
    auditQuery,
    createMutation,
    bulkMutation,
    updateMutation,
    toggleMutation,
    revealMutation,
    openEditModal,
    handleCopyAll,
    handleRevoke,
    openDetailWithParams,
    openDetailWithStats,
    closeCodeModal,
  };
}
