package com.example.service;

import org.springframework.stereotype.Service;
import com.example.repository.OrderRepository;
import com.example.repository.InventoryRepository;
import com.example.repository.AuditRepository;
import com.example.model.Order;

@Service
public class OrderService {

    private final OrderRepository orderRepo;
    private final InventoryRepository inventoryRepo;
    private final AuditRepository auditRepo;

    public OrderService(OrderRepository orderRepo,
                        InventoryRepository inventoryRepo,
                        AuditRepository auditRepo) {
        this.orderRepo = orderRepo;
        this.inventoryRepo = inventoryRepo;
        this.auditRepo = auditRepo;
    }

    public void placeOrder(Order order) {
        orderRepo.save(order);
        inventoryRepo.deductStock(order.getProductId(), order.getQuantity());
        auditRepo.logOrderCreated(order.getId());
    }
}
